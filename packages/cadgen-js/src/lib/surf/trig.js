// Engine-independent sine and cosine for the tessellator.
//
// WHY THIS EXISTS. `Math.sin` and `Math.cos` are not specified to any
// accuracy: ECMA-262 lets every implementation return its own approximation,
// and implementations disagree. Measured on identical arguments, V8 in Node 26
// and V8 in the snapshot browser (Chromium 151) return different bits for
// ~2.9% of `Math.sin` calls and ~2.8% of `Math.cos` calls over [-10, 10].
//
// Both engines tessellate the same components into the same content-addressed
// mesh store (one key per component + tolerances), and the exported GLB / STL /
// 3MF bytes are that tessellation. So an unspecified libm makes a document's
// exported bytes depend on WHICH engine reached the store first — a viewer or
// `cadgen step snapshot` warming the cache changed the GLB a later
// `cadgen glb build` wrote. That is cadgen law 5 (byte determinism); a
// tessellator that is shared by render and export has to be bit-identical in
// every engine that runs it.
//
// WHAT IT IS. The fdlibm/msun kernels — the same algorithm V8 itself ports —
// written in plain JavaScript. Every operation here is `+`, `-`, `*`, `/` or a
// comparison, all of which IEEE 754 defines to the bit and ECMA-262 requires
// exactly, so the result is the same on every engine and platform. Accuracy is
// fdlibm's: under 1 ulp, and exact where the kernels are (`sin(0)`, `cos(0)`).
//
// WHERE IT IS USED. Everything whose output reaches a stored tessellation:
// `evaluate.js` (analytic curves, surfaces and normals) and the tolerance
// thresholds in `tessellate.js`. Callers whose results never leave the process
// — view-dependent LOD, UI, diagnostics — may keep using `Math`.
//
// The other `Math` functions the tessellator uses are safe by specification:
// `sqrt` is correctly rounded, and `abs`/`min`/`max`/`round`/`floor`/`ceil`/
// `trunc`/`sign` are exact. `Math.hypot` is not specified to any accuracy
// either — the two engines happened to agree on all 20000 sample arguments,
// but the tessellation path uses `Math.sqrt` of the sum of squares instead, so
// no unspecified function survives anywhere the bytes come from.

// fdlibm __kernel_sin coefficients.
const S1 = -1.66666666666666324348e-01;
const S2 = 8.33333333332248946124e-03;
const S3 = -1.98412698298579493134e-04;
const S4 = 2.75573137070700676789e-06;
const S5 = -2.50507602534068634195e-08;
const S6 = 1.58969099521155010221e-10;

// fdlibm __kernel_cos coefficients.
const C1 = 4.16666666666666019037e-02;
const C2 = -1.38888888888741095749e-03;
const C3 = 2.48015872894767294178e-05;
const C4 = -2.75573143513906633035e-07;
const C5 = 2.08757232129817482790e-09;
const C6 = -1.13596475577881948265e-11;

// pi/4, and pi/2 split into three parts whose leading terms have enough
// trailing zero bits that `n * part` is exact for every integer n the medium
// range admits (fdlibm __ieee754_rem_pio2).
const PIO4 = 7.85398163397448278999e-01;
const INV_PIO2 = 6.36619772367581382433e-01;
const PIO2_1 = 1.57079632673412561417e+00;
const PIO2_1T = 6.07710050650619224932e-11;
const PIO2_2 = 6.07710050630396597660e-11;
const PIO2_2T = 2.02226624879595063154e-21;
const PIO2_3 = 2.02226624871116645580e-21;
const PIO2_3T = 8.47842766036889956997e-32;

// Below this the kernels are the identity: sin(x) rounds to x, cos(x) to 1.
const TINY = 3.725290298461914e-09; // 2^-28
// n * PIO2_1 is exact only while |n| stays inside 2^20, which bounds the
// argument. Radians past this are not a tessellation input — a surface
// parameter that large is already meaningless — so it fails loudly (law 10)
// instead of silently returning a reduction that lost its low bits.
const MAX_ARGUMENT = 524288; // 2^19

function kernelSin(x, tail, hasTail) {
  const z = x * x;
  const w = z * z;
  const r = S2 + z * (S3 + z * S4) + z * w * (S5 + z * S6);
  const v = z * x;
  if (!hasTail) return x + v * (S1 + z * r);
  return x - ((z * (0.5 * tail - v * r) - tail) - v * S1);
}

function kernelCos(x, tail) {
  const z = x * x;
  const w = z * z;
  const r = z * (C1 + z * (C2 + z * C3)) + w * w * (C4 + z * (C5 + z * C6));
  const hz = 0.5 * z;
  const a = 1 - hz;
  return a + (((1 - a) - hz) + (z * r - x * tail));
}

// Reduce x to r + tail with |r| <= pi/4, and the quadrant count n, so that
// x = n * (pi/2) + r + tail. Three Cody-Waite rounds, applied unconditionally:
// fdlibm skips the later ones when the first leaves no cancellation, which is
// a speed choice, not an accuracy one — running them always is at least as
// accurate and needs no bit inspection of the intermediate.
const reduced = { n: 0, r: 0, tail: 0 };

function reducePio2(x) {
  const n = Math.trunc(x * INV_PIO2 + (x > 0 ? 0.5 : -0.5));
  const fn = n;

  let r = x - fn * PIO2_1;
  let w = fn * PIO2_1T;

  let t = r;
  w = fn * PIO2_2;
  r = t - w;
  w = fn * PIO2_2T - ((t - r) - w);

  t = r;
  w = fn * PIO2_3;
  r = t - w;
  w = fn * PIO2_3T - ((t - r) - w);

  const head = r - w;
  reduced.n = n;
  reduced.r = head;
  reduced.tail = (r - head) - w;
  return reduced;
}

function outOfRange(x) {
  throw new RangeError(
    `deterministic sin/cos is defined for |x| < ${MAX_ARGUMENT} radians, got ${x}`,
  );
}

/** `Math.sin`, computed identically on every JavaScript engine. */
export function sin(x) {
  const ax = Math.abs(x);
  if (!Number.isFinite(x)) return NaN;
  if (ax <= PIO4) {
    if (ax < TINY) return x;
    return kernelSin(x, 0, false);
  }
  if (!(ax < MAX_ARGUMENT)) outOfRange(x);
  const { n, r, tail } = reducePio2(x);
  switch (n & 3) {
    case 0: return kernelSin(r, tail, true);
    case 1: return kernelCos(r, tail);
    case 2: return -kernelSin(r, tail, true);
    default: return -kernelCos(r, tail);
  }
}

/** `Math.cos`, computed identically on every JavaScript engine. */
export function cos(x) {
  const ax = Math.abs(x);
  if (!Number.isFinite(x)) return NaN;
  if (ax <= PIO4) {
    if (ax < TINY) return 1;
    return kernelCos(x, 0);
  }
  if (!(ax < MAX_ARGUMENT)) outOfRange(x);
  const { n, r, tail } = reducePio2(x);
  switch (n & 3) {
    case 0: return kernelCos(r, tail);
    case 1: return -kernelSin(r, tail, true);
    case 2: return -kernelCos(r, tail);
    default: return kernelSin(r, tail, true);
  }
}
