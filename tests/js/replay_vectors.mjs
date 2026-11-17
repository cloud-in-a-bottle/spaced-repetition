// Usage: node replay_vectors.mjs <vectors.json>. Prints the JS replay of each case as json, for test_js_fsrs.py.
import { readFileSync } from "node:fs";
import { replay } from "../../src/srs/static/js/fsrs.js";

const { settings, cases } = JSON.parse(readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(cases.map((c) => replay(c.created_at, c.reviews, settings))));
