#!/usr/bin/env node
// True-pose placement conformance: a model renders at its AUTHORED world
// coordinates in CAD and Render — never re-centered on its bounds — and the
// physical studio floor follows the model independently of world-space guides.
//
// Asserted through the read-only window.__cadModelPlacement seam CadViewer
// publishes when it places a model:
//
//   1. model group position is exactly (0,0,0) in every checked scene;
//   2. the authored bounds reach the page unchanged (the demo plate is an
//      origin-centered Box(60,40,4): authored z=[-2,2], top face at z=2);
//   3. CAD light/dark (floor off): gridFloorZ === 0 and
//      floorFollowsModel === false;
//   4. Light/Dark studio (floor on): followModel may act independently of guides.
//
// Usage:
//   node scripts/e2e-model-placement.mjs --dir <models-root>
//        [--url http://127.0.0.1:3245] [--file projects/demo-plate/STEP/plate.step]
//        [--out <dir>]
//
// Requires a viewer already serving <models-root> and playwright available.
// Exits non-zero on any violation.

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

const EXPECTATIONS = [
  { id: "cad-light", appearance: "Light", floorEnabled: false },
  { id: "cad-dark", appearance: "Dark", floorEnabled: false },
  { id: "render-light", appearance: "Light", render: true, floorEnabled: true },
  { id: "render-dark", appearance: "Dark", render: true, floorEnabled: true }
];

async function configureScene(page, expectation) {
  await page.getByRole("button", { name: "Appearance", exact: true }).click();
  await page.getByRole("menuitemradio", { name: expectation.appearance, exact: true }).click();
  if (!expectation.render) {
    return;
  }
  await page.getByRole("button", { name: /^Viewing mode:/ }).click();
  await page.getByRole("menuitemradio", { name: "Render", exact: true }).click();
}

function parseArgs(argv) {
  const args = { url: "http://127.0.0.1:3245", file: "projects/demo-plate/STEP/plate.step" };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const next = argv[index + 1];
    args[token.slice(2)] = next === undefined || next.startsWith("--") ? "true" : (index += 1, next);
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));
if (!args.dir) {
  console.error("--dir <models-root> is required (the root the running viewer serves)");
  process.exit(2);
}
const modelPath = path.join(path.resolve(args.dir), args.file);
if (!fs.existsSync(modelPath)) {
  console.error(`fixture missing under the served models root: ${modelPath}`);
  process.exit(2);
}

const { chromium } = require("playwright");

const failures = [];
const browser = await chromium.launch({
  args: ["--use-angle=metal"]
});

for (const expectation of EXPECTATIONS) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const url = `${args.url}?file=${encodeURIComponent(args.file)}`;
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: /^Viewing mode:/ }).waitFor({ timeout: 30000 });
  await configureScene(page, expectation);
  let placement = null;
  try {
    await page.waitForFunction(
      (floorEnabled) => (
        Boolean(window.__cadModelPlacement?.position) &&
        window.__cadModelPlacement.floorFollowsModel === floorEnabled
      ),
      expectation.floorEnabled,
      { timeout: 30000 }
    );
    placement = await page.evaluate(() => window.__cadModelPlacement);
  } catch {
    failures.push(`${expectation.id}: placement seam never reached the expected scene state`);
  }

  if (placement) {
    const [px, py, pz] = placement.position.map(Number);
    if (Math.abs(px) > 1e-9 || Math.abs(py) > 1e-9 || Math.abs(pz) > 1e-9) {
      failures.push(
        `${expectation.id}: model translated to [${placement.position}] — must render at authored coordinates`
      );
    }
    const minZ = Number(placement.boundsMin?.[2]);
    const maxZ = Number(placement.boundsMax?.[2]);
    // The demo plate is an origin-centered Box(60,40,4): authored z=[-2,2].
    // A re-centering regression cannot fake this: it changes world position,
    // not bounds — so pair the bounds check with the position check above.
    if (!(Math.abs(minZ + 2) < 1e-6 && Math.abs(maxZ - 2) < 1e-6)) {
      failures.push(
        `${expectation.id}: expected authored plate bounds z=[-2,2], got z=[${minZ},${maxZ}] — wrong fixture?`
      );
    }
    if (expectation.floorEnabled) {
      if (placement.floorFollowsModel !== true) {
        failures.push(`${expectation.id}: floor-enabled stage should keep followModel available`);
      }
      // The plate dips to z=-2, so a floor-enabled stage follows it DOWN to the
      // model bottom (downward-only follow, no clipping).
      if (Math.abs(Number(placement.gridFloorZ) + 2) > 1e-6) {
        failures.push(`${expectation.id}: stage should follow the model down to z=-2, got ${placement.gridFloorZ}`);
      }
    } else {
      if (placement.floorFollowsModel !== false) {
        failures.push(`${expectation.id}: followModel must be inert with the floor disabled`);
      }
      if (placement.gridFloorZ !== null && Math.abs(Number(placement.gridFloorZ)) > 1e-6) {
        failures.push(`${expectation.id}: stage floor must stay at world z=0, got ${placement.gridFloorZ}`);
      }
    }
    console.log(
      `${expectation.id}: position=[${placement.position}] boundsZ=[${placement.boundsMin?.[2]},${placement.boundsMax?.[2]}] ` +
      `gridFloorZ=${placement.gridFloorZ} follow=${placement.floorFollowsModel}`
    );
  }

  if (args.out) {
    fs.mkdirSync(args.out, { recursive: true });
    await page.waitForTimeout(1200);
    fs.writeFileSync(
      path.join(args.out, `placement-${expectation.id}.png`),
      await page.screenshot()
    );
  }
  await context.close();
}

await browser.close();

if (failures.length) {
  console.error("\nPLACEMENT FAILURES:");
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log("\nmodel placement conformance: OK");
