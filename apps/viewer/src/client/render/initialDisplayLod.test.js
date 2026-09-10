import assert from "node:assert/strict";
import test from "node:test";

import {
  COARSE_SURF_DECODE_EXPANSION_ESTIMATE,
  DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE,
  LARGE_ASSEMBLY_INITIAL_COARSE_COMPONENTS,
  estimateInitialSurfDecodeBytes,
  initialDisplayLodPlan,
} from "./initialDisplayLod.js";

const MIB = 1024 * 1024;

test("large assemblies start coarse while small and medium packages keep the default", () => {
  assert.equal(initialDisplayLodPlan({ componentCount: 9, maxInFlightBytes: 256 * MIB }).level, 1);
  const large = initialDisplayLodPlan({
    componentCount: LARGE_ASSEMBLY_INITIAL_COARSE_COMPONENTS,
    maxInFlightBytes: 256 * MIB,
  });
  assert.equal(large.level, 0);
  assert.equal(large.reason, "large-assembly");
  assert.equal(large.sourceExpansionRatio, COARSE_SURF_DECODE_EXPANSION_ESTIMATE);
});

test("any oversized leaf tries coarse only when its independent estimate fits", () => {
  assert.equal(initialDisplayLodPlan({
    componentCount: 9,
    surfBytes: 1 * MIB,
    maxInFlightBytes: 256 * MIB,
  }).level, 1, "the other leaves in the same small assembly stay at the default");
  const coarse = initialDisplayLodPlan({
    componentCount: 9,
    surfBytes: 5 * MIB,
    maxInFlightBytes: 256 * MIB,
  });
  assert.equal(coarse.level, 0);
  assert.equal(coarse.reason, "component-admission");
  assert.equal(coarse.estimatedBytes, 160 * MIB);
  assert.equal(coarse.fitsDecodeCap, true);

  const refused = initialDisplayLodPlan({
    componentCount: 9,
    surfBytes: 9 * MIB,
    maxInFlightBytes: 256 * MIB,
  });
  assert.equal(refused.level, 0);
  assert.equal(refused.estimatedBytes, 288 * MIB);
  assert.equal(refused.fitsDecodeCap, false);
  assert.equal(
    estimateInitialSurfDecodeBytes(5 * MIB, DEFAULT_SURF_DECODE_EXPANSION_ESTIMATE),
    320 * MIB,
  );
});
