// Engine-independent sin/cos (trig.js). Two things have to hold: the values
// are as good as `Math`'s (within one ulp, and exact where the answer is
// exact), and nothing on the way to a stored tessellation still calls a
// `Math` function that ECMA-262 leaves to the implementation.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { cos, sin } from "./trig.js";

const view = new DataView(new ArrayBuffer(16));

function ulpsApart(a, b) {
  if (Object.is(a, b)) return 0;
  view.setFloat64(0, a);
  view.setFloat64(8, b);
  let x = view.getBigInt64(0);
  let y = view.getBigInt64(8);
  // Map the sign-magnitude doubles onto a monotone integer line.
  if (x < 0n) x = -9223372036854775808n - x;
  if (y < 0n) y = -9223372036854775808n - y;
  return Number(x > y ? x - y : y - x);
}

function* samples(count) {
  // A fixed LCG, so the same arguments are tested on every run and engine.
  let state = 12345;
  const next = () => {
    state = (state * 1103515245 + 12345) % 2147483648;
    return state / 2147483648;
  };
  for (let i = 0; i < count; i += 1) {
    const span = [0.5, 2, 20, 2000][i % 4];
    yield (next() - 0.5) * span;
  }
}

test("deterministic sin/cos stay within one ulp of the engine's own", () => {
  let worstSin = 0;
  let worstCos = 0;
  for (const x of samples(50000)) {
    worstSin = Math.max(worstSin, ulpsApart(sin(x), Math.sin(x)));
    worstCos = Math.max(worstCos, ulpsApart(cos(x), Math.cos(x)));
  }
  assert.ok(worstSin <= 1, `sin is ${worstSin} ulps from Math.sin`);
  assert.ok(worstCos <= 1, `cos is ${worstCos} ulps from Math.cos`);
});

test("the values that must be exact are exact", () => {
  assert.ok(Object.is(sin(0), 0));
  assert.equal(cos(0), 1);
  assert.equal(sin(Math.PI / 2), 1);
  assert.equal(cos(Math.PI), -1);
  assert.equal(sin(-Math.PI / 2), -1);
  // The cardinal quarter turns: not zero, because the double nearest pi/2 is
  // not pi/2 — but the SAME not-zero every engine computes, which is the whole
  // point. These are the values the cylinder-seam normals in an exported GLB
  // are made of.
  assert.equal(cos(Math.PI / 2), 6.123233995736766e-17);
  assert.equal(sin(Math.PI), 1.2246467991473532e-16);
  assert.equal(cos(3 * Math.PI / 2), -1.8369701987210297e-16);
  assert.equal(sin(2 * Math.PI), -2.4492935982947064e-16);
});

test("odd/even symmetry survives argument reduction", () => {
  for (const x of samples(2000)) {
    assert.ok(Object.is(sin(-x), -sin(x)) || sin(x) === 0, `sin(${-x})`);
    assert.equal(cos(-x), cos(x), `cos(${-x})`);
  }
});

test("non-finite arguments answer NaN and absurd ones fail loudly", () => {
  assert.ok(Number.isNaN(sin(NaN)));
  assert.ok(Number.isNaN(cos(Infinity)));
  assert.ok(Number.isNaN(sin(-Infinity)));
  assert.throws(() => sin(1e9), RangeError);
  assert.throws(() => cos(-1e9), RangeError);
  // Just inside the limit still answers.
  assert.ok(Number.isFinite(cos(524287)));
});

test("nothing on the tessellation path calls an unspecified Math function", () => {
  // `Math.sin`/`cos`/`tan`/`hypot`/`atan2`/`log`/`exp`/`pow` are implementation
  // approximations: Node's engine and the snapshot browser's disagree on ~3% of
  // arguments. Anything whose result is encoded into a content-addressed
  // tessellation has to avoid them, or the same document exports different
  // bytes depending on which one filled the cache (cadgen law 5).
  for (const name of ["evaluate.js", "tessellate.js", "trig.js"]) {
    const source = readFileSync(new URL(name, import.meta.url), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .split("\n")
      .filter((line) => !line.trimStart().startsWith("//"))
      .join("\n");
    const found = source.match(/Math\.(sin|cos|tan|asin|acos|atan|atan2|hypot|log|exp|pow|cbrt)\b/g);
    assert.equal(found, null, `${name} uses ${found?.join(", ")}`);
  }
});
