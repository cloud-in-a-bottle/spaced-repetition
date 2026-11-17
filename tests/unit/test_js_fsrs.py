import json
import random
import shutil
import subprocess
from pathlib import Path

import attr
import pytest

from srs.domain.schedule import Rating
from srs.domain.schedule import Review
from srs.domain.settings import Settings
from srs.scheduling.replay import replay

_SCRIPT = Path(__file__).parent.parent / "js" / "replay_vectors.mjs"
_MINUTE = 60_000
_GAPS = [0, _MINUTE, 5 * _MINUTE, 3600_000, 86_400_000, 2 * 86_400_000, 9 * 86_400_000, 40 * 86_400_000]


def _random_case(rng: random.Random, n: int) -> tuple[int, list[Review]]:
    created = 1_700_000_000_000 + rng.randrange(10**9)
    t = created + rng.randrange(10**8)
    reviews = []
    for i in range(n):
        t += rng.choice(_GAPS) + rng.randrange(_MINUTE)
        reviews.append(Review(f"r{n}-{i}-{rng.random()}", "c", Rating(rng.choice([1, 2, 3, 3, 3, 4])), t, None, "x"))
    return created, reviews


@pytest.mark.parametrize(
    "settings",
    [
        Settings(),
        Settings(desired_retention=0.8, learning_steps_minutes=[], relearning_steps_minutes=[]),
        Settings(learning_steps_minutes=[1, 10, 60], relearning_steps_minutes=[5, 30], maximum_interval_days=30),
    ],
)
def test_js_replay_matches_python(tmp_path: Path, settings: Settings) -> None:
    node = shutil.which("node")
    assert node is not None, "node is needed to test the browser scheduler"
    rng = random.Random(42)
    cases = [_random_case(rng, rng.randrange(1, 25)) for _ in range(300)]
    vectors = {
        "settings": attr.asdict(settings),
        "cases": [
            {
                "created_at": c,
                "reviews": [{"id": r.id, "rating": int(r.rating), "reviewed_at": r.reviewed_at} for r in rs],
            }
            for c, rs in cases
        ],
    }
    path = tmp_path / "vectors.json"
    path.write_text(json.dumps(vectors))
    out = subprocess.run([node, str(_SCRIPT), str(path)], capture_output=True, text=True, check=True).stdout
    js_results = json.loads(out)
    for (created, reviews), js in zip(cases, js_results, strict=True):
        py = attr.asdict(replay(created, reviews, settings))
        assert js["state"] == py["state"]
        assert js["step"] == py["step"]
        assert js["due"] == py["due"], (reviews, js, py)
        assert js["last_review"] == py["last_review"]
        assert (js["reps"], js["lapses"]) == (py["reps"], py["lapses"])
        assert js["stability"] == pytest.approx(py["stability"], rel=1e-9)
        assert js["difficulty"] == pytest.approx(py["difficulty"], rel=1e-9)
