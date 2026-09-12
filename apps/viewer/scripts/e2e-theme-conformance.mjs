#!/usr/bin/env node
// Do CAD appearance and Render studios actually reach the pixels?
//
// CAD appearance and Render studios share one mesh renderer. This drives the current
// navbar and Render-tab controls, then records the background and model surface.
//
// It asserts that the model pixels change across those real settings. A renderer that
// ignores lighting can still start and draw while every pass looks identical.
//
// Usage:
//   node scripts/e2e-theme-conformance.mjs --dir <models-root> [--url http://127.0.0.1:3245]
//                                          [--out <dir>] [--baseline <file>]
//
// Requires a viewer already serving <models-root> (npm run start) and
// playwright available. Exits non-zero on a parity failure or an unresponsive surface.

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

const SCENE_SETTINGS = [
  { id: "cad-light", appearance: "Light", render: false },
  { id: "cad-dark", appearance: "Dark", render: false },
  { id: "render-adaptive-light", appearance: "Light", render: true },
  { id: "render-adaptive-dark", appearance: "Dark", render: true },
  { id: "render-light-pinned", appearance: "Dark", render: true, studio: "Light studio" },
  { id: "render-dark-pinned", appearance: "Light", render: true, studio: "Dark studio" }
];

// One scene per RENDERER, not per format. The mesh fixture is an STL because it loads with
// no build step, so the scene sweep does not spend package rebuilds proving a point
// about lighting.
const SCENES = [
  { renderer: "mesh", file: "fun/miniature_spiral_staircase_highres.stl" }
];

const VIEWPORT = { width: 1440, height: 900 };
// Top-left of the viewport: stage backdrop under every fixture, clear of the toolbar, the
// file sheet and the model itself.
const BACKGROUND_CLIP = { x: 24, y: 120, width: 160, height: 160 };
// The middle band, where each fixture's geometry actually sits.
const SURFACE_CLIP = { x: 260, y: 240, width: 520, height: 420 };

function parseArgs(argv) {
  const args = { url: "http://127.0.0.1:3245", dir: "", out: "", baseline: "" };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === "--url") args.url = argv[++index] || args.url;
    else if (flag === "--dir") args.dir = argv[++index] || "";
    else if (flag === "--out") args.out = argv[++index] || "";
    else if (flag === "--baseline") args.baseline = argv[++index] || "";
  }
  return args;
}

function meanRgb(png) {
  let r = 0;
  let g = 0;
  let b = 0;
  let n = 0;
  for (let index = 0; index < png.data.length; index += 4) {
    r += png.data[index];
    g += png.data[index + 1];
    b += png.data[index + 2];
    n += 1;
  }
  return n ? [r / n, g / n, b / n] : [0, 0, 0];
}

function rgbDistance(a, b) {
  return Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1]), Math.abs(a[2] - b[2]));
}

async function configureScene(page, setting) {
  await page.getByRole("button", { name: "Appearance", exact: true }).click();
  await page.getByRole("menuitemradio", { name: setting.appearance, exact: true }).click();
  if (!setting.render) {
    return;
  }
  await page.getByRole("tab", { name: "Render", exact: true }).click();
  const enabled = page.getByRole("switch", { name: "Enabled", exact: true });
  if (!(await enabled.isChecked())) {
    await enabled.click();
  }
  if (setting.studio) {
    await page.getByRole("combobox", { name: "Studio", exact: true }).click();
    await page.getByRole("option", { name: setting.studio, exact: true }).click();
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.dir) {
    console.error("--dir <models-root> is required (absolute path the viewer is serving)");
    process.exit(2);
  }
  const modelsRoot = path.resolve(args.dir);
  // The URL no longer names the directory, so a viewer launched from the wrong directory would
  // just render nothing after a 9s wait per scene. Fail here instead, on the same paths
  // the viewer will be asked for.
  const missing = SCENES.map(({ file }) => file).filter((file) => !fs.existsSync(path.join(modelsRoot, file)));
  if (missing.length) {
    console.error(`scenes missing under ${modelsRoot} (is the viewer serving this root?):`);
    for (const file of missing) console.error(`  ${file}`);
    process.exit(2);
  }
  const { chromium } = require("playwright");
  const { PNG } = require("pngjs");

  const browser = await chromium.launch({ args: ["--use-angle=metal", "--ignore-gpu-blocklist"] });
  const results = [];

  for (const scene of SCENES) {
    for (const setting of SCENE_SETTINGS) {
      // Fresh context per pass keeps model session state independent.
      const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1 });
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (error) => errors.push(String(error).slice(0, 160)));

      // The viewer under test must already be serving modelsRoot (its launch cwd).
      const url = `${args.url}?file=${encodeURIComponent(scene.file)}`;
      await page.goto(url, { waitUntil: "domcontentloaded" });
      await page.getByRole("tab", { name: "Render", exact: true }).waitFor({ timeout: 30000 });
      await configureScene(page, setting);
      await page.waitForTimeout(9000);

      const activeAppearance = await page.evaluate(() => (
        document.documentElement.classList.contains("dark") ? "Dark" : "Light"
      ));
      const renderEnabled = setting.render
        ? await page.getByRole("switch", { name: "Enabled", exact: true }).isChecked()
        : false;
      const activeStudio = setting.render
        ? String(await page.getByRole("combobox", { name: "Studio", exact: true }).textContent() || "").trim()
        : "";

      const backgroundPng = PNG.sync.read(await page.screenshot({ clip: BACKGROUND_CLIP }));
      const surfacePng = PNG.sync.read(await page.screenshot({ clip: SURFACE_CLIP }));
      if (args.out) {
        fs.mkdirSync(args.out, { recursive: true });
        fs.writeFileSync(
          path.join(args.out, `${scene.renderer}-${setting.id}.png`),
          await page.screenshot({ clip: SURFACE_CLIP })
        );
      }

      results.push({
        renderer: scene.renderer,
        settingId: setting.id,
        expectedAppearance: setting.appearance,
        activeAppearance,
        expectedStudio: setting.studio || "",
        activeStudio,
        renderEnabled,
        background: meanRgb(backgroundPng).map((value) => Number(value.toFixed(2))),
        surface: meanRgb(surfacePng).map((value) => Number(value.toFixed(2))),
        errors: errors.slice(0, 2)
      });
      await context.close();
    }
  }

  await browser.close();

  const failures = [];
  for (const result of results) {
    if (result.activeAppearance !== result.expectedAppearance) {
      failures.push(`${result.renderer}/${result.settingId}: viewer used ${result.activeAppearance} appearance`);
    }
    if (result.settingId.includes("render") && !result.renderEnabled) {
      failures.push(`${result.renderer}/${result.settingId}: Render did not remain enabled`);
    }
    if (result.expectedStudio && !result.activeStudio.includes(result.expectedStudio)) {
      failures.push(`${result.renderer}/${result.settingId}: expected ${result.expectedStudio}, saw ${result.activeStudio}`);
    }
    for (const error of result.errors) {
      failures.push(`${result.renderer}/${result.settingId}: page error ${error}`);
    }
  }

  // Surface response: each renderer must actually look different across settings.
  console.log("surface response across CAD/Render settings (must not be flat):");
  for (const scene of SCENES) {
    const passes = results.filter((result) => result.renderer === scene.renderer);
    let spread = 0;
    for (const a of passes) {
      for (const b of passes) spread = Math.max(spread, rgbDistance(a.surface, b.surface));
    }
    const ok = spread > 4;
    if (!ok) failures.push(`${scene.renderer}: surface is identical across all settings (spread ${spread.toFixed(1)}/255)`);
    console.log(`  ${ok ? "ok  " : "FAIL"} ${scene.renderer.padEnd(9)} spread=${spread.toFixed(1)}/255`);
    for (const pass of passes) console.log(`         ${pass.settingId.padEnd(24)} ${pass.surface}`);

    const lightStudio = passes.find((pass) => pass.settingId === "render-light-pinned");
    const darkStudio = passes.find((pass) => pass.settingId === "render-dark-pinned");
    const studioSpread = lightStudio && darkStudio ? rgbDistance(lightStudio.surface, darkStudio.surface) : 0;
    if (studioSpread <= 4) failures.push(`${scene.renderer}: Light studio and Dark studio are visually identical`);
  }

  if (args.baseline) {
    fs.mkdirSync(path.dirname(path.resolve(args.baseline)), { recursive: true });
    fs.writeFileSync(path.resolve(args.baseline), `${JSON.stringify(results, null, 2)}\n`);
    console.log(`\nbaseline written to ${args.baseline}`);
  }

  if (failures.length) {
    console.log("\nfailures:");
    for (const failure of failures) console.log(`  ${failure}`);
  } else {
    console.log("\nevery CAD/Render setting reaches the surface");
  }
  process.exit(failures.length ? 1 : 0);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
