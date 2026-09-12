import assert from "node:assert/strict";
import test from "node:test";
import { buildViewerMeshAlert } from "./viewerAlerts.js";

const step = { file: "STEP/moonwatch.step", kind: "part" };

test("connection failure explains recovery without blaming the compiler", () => {
  const alert = buildViewerMeshAlert(step, false, "", {
    status: "failed", error: "Failed to fetch",
    failure: { kind: "network", method: "GET", operation: "checking display assets", url: "/__cad/artifact?file=STEP%2Fmoonwatch.step" }
  });
  assert.equal(alert.summary, "Connection lost");
  assert.match(alert.title, /reach the viewer/);
  assert.match(alert.message, /checking display assets.*moonwatch.step/);
  assert.match(alert.message, /viewer is running/);
  assert.match(alert.details, /Request: GET/);
  assert.equal(alert.reload, true);
});

test("disconnected POST warns that the build may still be running", () => {
  const alert = buildViewerMeshAlert(step, false, "", {
    status: "failed", error: "Load failed", failure: { kind: "network", method: "POST" }
  });
  assert.match(alert.recovery, /may still be running/);
  assert.doesNotMatch(alert.title, /compil/i);
});

test("HTTP error reports status and the server's reason", () => {
  const alert = buildViewerMeshAlert(step, false, "", {
    status: "failed", error: "Worker unavailable", failure: { kind: "http", status: 503 }
  });
  assert.match(alert.message, /HTTP 503/);
  assert.equal(alert.reason, "Worker unavailable");
  assert.match(alert.details, /HTTP status: 503/);
});

test("compile failure preserves the full diagnostic, context and useful recovery", () => {
  const reason = "Unsupported DXF entity HATCH\n" + "compiler diagnostic ".repeat(500).trim();
  const alert = buildViewerMeshAlert({ file: "drawings/plate.dxf", kind: "dxf" }, false, "", { status: "failed", error: reason });
  assert.equal(alert.summary, "Compile failed");
  assert.equal(alert.reason, reason);
  assert.ok(alert.details.endsWith(reason));
  assert.match(alert.message, /plate.dxf/);
  assert.match(alert.recovery, /terminal output/);
  assert.match(alert.recovery, /rebuild/);
});

test("missing compiler diagnostic is stated honestly", () => {
  const alert = buildViewerMeshAlert(step, false, "", { status: "failed", error: "" });
  assert.match(alert.reason, /No diagnostic was returned/);
  assert.match(alert.recovery, /terminal output/);
});

test("an artifact failure is not raised once geometry is visible", () => {
  assert.equal(buildViewerMeshAlert(step, true, "", { status: "failed", error: "boom" }), null);
});

test("failed STEP artifact explains what is missing and retains a renderable fallback", () => {
  for (const [code, reason] of [["missing_glb", "Generated GLB is missing"], ["missing_source_path", "missing its source path"]]) {
    const entry = { ...step, artifact: { ok: false, error: code, message: "Original diagnostic" } };
    const alert = buildViewerMeshAlert(entry, false, "");
    assert.equal(alert.severity, "error");
    assert.ok(alert.message.includes(reason));
    assert.match(alert.details, /Original diagnostic/);
    assert.equal(buildViewerMeshAlert(entry, true, ""), null);
    const fallback = { ...entry, url: "/models/.part.step.glb", hash: "glb-hash" };
    const warning = buildViewerMeshAlert(fallback, false, "");
    assert.equal(warning.severity, "warning");
    assert.equal(warning.blocking, false);
    const failedFallback = buildViewerMeshAlert(fallback, false, "GLB parser failed");
    assert.equal(failedFallback.summary, "Mesh load failed");
    assert.match(failedFallback.reason, /GLB parser failed/);
  }
});

test("mesh errors also recognize browser transport messages", () => {
  for (const kind of ["stl", "3mf", "glb", "dxf"]) {
    const entry = { file: `parts/panel.${kind}`, kind };
    const alert = buildViewerMeshAlert(entry, false, "Failed to fetch");
    assert.equal(alert.summary, "Connection lost");
    assert.match(alert.message, /loading geometry/);
    assert.equal(buildViewerMeshAlert(entry, false, "Invalid file header").reason, "Invalid file header");
  }
});

test("missing geometry gives file context and a next step; empty drawings stay valid", () => {
  const alert = buildViewerMeshAlert({ file: "meshes/part.stl", kind: "stl" }, false, "");
  assert.equal(alert.summary, "Mesh unavailable");
  assert.match(alert.message, /meshes\/part.stl/);
  assert.match(alert.recovery, /saved completely/);
  const drawing = { file: "plans/panel.dxf.py", kind: "dxf" };
  assert.equal(buildViewerMeshAlert(drawing, false, ""), null);
  assert.equal(buildViewerMeshAlert(drawing, false, "bad DXF").summary, "Mesh load failed");
  assert.equal(buildViewerMeshAlert(null, false, "failure"), null);
});
