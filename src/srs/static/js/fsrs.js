// FSRS-6 scheduling, ported from py-fsrs (which the server uses) so the app can schedule while offline.
// The server stays authoritative: on sync it replays all reviews and its result replaces ours.
// tests/unit/test_js_fsrs.py checks this file against the server's implementation.

export const DAY_MS = 86_400_000;
const MINUTE_MS = 60_000;
const STABILITY_MIN = 0.001;
const FUZZ_RANGES = [
  [2.5, 7.0, 0.15],
  [7.0, 20.0, 0.1],
  [20.0, Infinity, 0.05],
];

// Python's round(): halves go to the even neighbour.
function roundHalfEven(x) {
  const r = Math.round(x);
  return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
}

const clampD = (d) => Math.min(Math.max(d, 1), 10);
const clampS = (s) => Math.max(s, STABILITY_MIN);

export function seededUnitFloat(seed) {
  let h = 0x811c9dc5;
  for (const byte of new TextEncoder().encode(seed)) {
    h ^= byte;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h / 2 ** 32;
}

export function fuzzedIntervalDays(intervalDays, maximumIntervalDays, seed) {
  if (intervalDays < 2.5) return intervalDays;
  let delta = 1.0;
  for (const [start, end, factor] of FUZZ_RANGES) {
    delta += factor * Math.max(Math.min(intervalDays, end) - start, 0);
  }
  let minIvl = Math.max(2, roundHalfEven(intervalDays - delta));
  const maxIvl = Math.min(roundHalfEven(intervalDays + delta), maximumIntervalDays);
  minIvl = Math.min(minIvl, maxIvl);
  const fuzzed = Math.floor(seededUnitFloat(seed) * (maxIvl - minIvl + 1)) + minIvl;
  return Math.min(fuzzed, maximumIntervalDays);
}

class Model {
  constructor(settings) {
    this.w = settings.fsrs_parameters;
    this.settings = settings;
    this.decay = -this.w[20];
    this.factor = 0.9 ** (1 / this.decay) - 1;
  }
  retrievability(elapsedDays, s) {
    return (1 + (this.factor * elapsedDays) / s) ** this.decay;
  }
  initialStability(r) {
    return clampS(this.w[r - 1]);
  }
  initialDifficulty(r, clamp) {
    const d = this.w[4] - Math.E ** (this.w[5] * (r - 1)) + 1;
    return clamp ? clampD(d) : d;
  }
  nextInterval(s) {
    const ivl = roundHalfEven((s / this.factor) * (this.settings.desired_retention ** (1 / this.decay) - 1));
    return Math.min(Math.max(ivl, 1), this.settings.maximum_interval_days);
  }
  shortTermStability(s, r) {
    let inc = Math.E ** (this.w[17] * (r - 3 + this.w[18])) * s ** -this.w[19];
    if (r >= 2) inc = Math.max(inc, 1.0);
    return clampS(s * inc);
  }
  nextDifficulty(d, r) {
    const delta = -(this.w[6] * (r - 3));
    const damped = d + ((10 - d) * delta) / 9;
    return clampD(this.w[7] * this.initialDifficulty(4, false) + (1 - this.w[7]) * damped);
  }
  nextStability(d, s, ret, r) {
    const w = this.w;
    let next;
    if (r === 1) {
      const long = w[11] * d ** -w[12] * ((s + 1) ** w[13] - 1) * Math.E ** ((1 - ret) * w[14]);
      const short = s / Math.E ** (w[17] * w[18]);
      next = Math.min(long, short);
    } else {
      const hard = r === 2 ? w[15] : 1;
      const easy = r === 4 ? w[16] : 1;
      next = s * (1 + Math.E ** w[8] * (11 - d) * s ** -w[9] * (Math.E ** ((1 - ret) * w[10]) - 1) * hard * easy);
    }
    return clampS(next);
  }
}

function stepInterval(steps, step, rating) {
  // returns [newStep, intervalMs] or null when the card graduates to review
  switch (rating) {
    case 1:
      return [0, steps[0] * MINUTE_MS];
    case 2:
      if (step === 0 && steps.length === 1) return [step, steps[0] * 1.5 * MINUTE_MS];
      if (step === 0 && steps.length >= 2) return [step, ((steps[0] + steps[1]) / 2) * MINUTE_MS];
      return [step, steps[step] * MINUTE_MS];
    case 3:
      if (step + 1 === steps.length) return null;
      return [step + 1, steps[step + 1] * MINUTE_MS];
    case 4:
      return null;
  }
  throw new Error(`bad rating ${rating}`);
}

export function newSchedule(createdAt) {
  return {
    state: "new", step: 0, stability: null, difficulty: null,
    due: createdAt, last_review: null, reps: 0, lapses: 0,
  };
}

// Apply one review ({id, rating, reviewed_at}) to a schedule, returning the new schedule.
export function applyReview(schedule, review, settings) {
  const m = new Model(settings);
  const r = review.rating;
  const t = review.reviewed_at;
  let { state, step, stability: s, difficulty: d } = schedule;
  const lapses = schedule.lapses + (state === "review" && r === 1 ? 1 : 0);
  const daysSince = schedule.last_review === null ? null : Math.floor((t - schedule.last_review) / DAY_MS);
  const ret = () => (s === null ? 0 : m.retrievability(Math.max(0, daysSince ?? 0), s));
  if (state === "new") state = "learning";

  if (s === null || d === null) {
    s = m.initialStability(r);
    d = m.initialDifficulty(r, true);
  } else if (daysSince !== null && daysSince < 1) {
    s = m.shortTermStability(s, r);
    d = m.nextDifficulty(d, r);
  } else {
    s = m.nextStability(d, s, ret(), r);
    d = m.nextDifficulty(d, r);
  }

  let intervalMs;
  const graduate = () => {
    state = "review";
    step = null;
    intervalMs = m.nextInterval(s) * DAY_MS;
  };
  if (state === "review") {
    if (r === 1 && settings.relearning_steps_minutes.length > 0) {
      state = "relearning";
      step = 0;
      intervalMs = settings.relearning_steps_minutes[0] * MINUTE_MS;
    } else {
      intervalMs = m.nextInterval(s) * DAY_MS;
    }
  } else {
    const steps = state === "learning" ? settings.learning_steps_minutes : settings.relearning_steps_minutes;
    if (steps.length === 0 || (step >= steps.length && r >= 2)) {
      graduate();
    } else {
      const next = stepInterval(steps, step, r);
      if (next === null) graduate();
      else [step, intervalMs] = next;
    }
  }
  if (state === "review") {
    const days = Math.round(intervalMs / DAY_MS);
    intervalMs = fuzzedIntervalDays(days, settings.maximum_interval_days, review.id) * DAY_MS;
  }
  return {
    state, step, stability: s, difficulty: d,
    due: t + intervalMs, last_review: t, reps: schedule.reps + 1, lapses,
  };
}

export function replay(createdAt, reviews, settings) {
  const sorted = [...reviews].sort((a, b) => a.reviewed_at - b.reviewed_at || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return sorted.reduce((sched, rev) => applyReview(sched, rev, settings), newSchedule(createdAt));
}

export function retrievability(schedule, now, settings) {
  if (schedule.last_review === null || schedule.stability === null) return 0;
  const elapsed = Math.max(0, Math.floor((now - schedule.last_review) / DAY_MS));
  return new Model(settings).retrievability(elapsed, schedule.stability);
}
