#!/usr/bin/env node
// Isolated dense-component picking with the actual worker from a served viewer.
// Does not start/stop the viewer. --tess is an existing canonical cache object.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { viewerRuntimeFingerprint, verifyServedViewerClient } from './fingerprint.mjs';
import { decodeComponentTessellation } from '../../../packages/cadgen-js/src/lib/surf/tessellationCache.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const args = {};
for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
if (!args.url || !args.tess || !args.out) throw new Error('Required: --url ORIGIN --tess EXISTING_TESS --out JSON');
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_FROM || '/Users/jakefitzgerald/robots/text-to-cad/apps/viewer/node_modules/playwright');
const { build } = createRequire(path.join(root, 'apps/viewer/package.json'))('esbuild');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const runtimeFingerprintAtStart = viewerRuntimeFingerprint();
const servedClientProof = await verifyServedViewerClient(args.url);
const dist = path.join(root, 'apps/viewer/dist');
const workerFile = fs.readdirSync(path.join(dist, 'assets')).filter(name => /^raycastBvhWorker-.*\.js$/.test(name));
if (workerFile.length !== 1) throw new Error('Expected exactly one bundled surface BVH worker');
const workerUrl = new URL(`/assets/${workerFile[0]}`, args.url).href;
const workerResponse = await fetch(workerUrl, { cache: 'no-store' });
const workerBytes = Buffer.from(await workerResponse.arrayBuffer());
if (!workerResponse.ok || !workerBytes.equals(fs.readFileSync(path.join(dist, 'assets', workerFile[0])))) throw new Error('Served BVH worker bytes mismatch');
const input = fs.readFileSync(args.tess);
const { component } = decodeComponentTessellation(input);
const payload = Object.fromEntries([['position', component.positions], ['index', component.indices]].map(([name, array]) => [name, Buffer.from(array.buffer, array.byteOffset, array.byteLength)]));
const bundle = await build({ entryPoints: [path.join(root, 'scripts/bench/viewer-memory/picking-browser.mjs')], bundle: true, write: false, format: 'iife', platform: 'browser', logLevel: 'silent' });
const server = http.createServer((request, response) => {
  const bytes = payload[request.url.slice(1)];
  response.writeHead(bytes ? 200 : 404, { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/octet-stream' });
  response.end(bytes);
});
await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
let browser;
const pageErrors = [];
try {
  browser = await chromium.launch({ headless: true, args: ['--disable-features=PrivateNetworkAccessSendPreflights'] });
  const page = await browser.newPage();
  page.on('pageerror', error => pageErrors.push(String(error)));
  await page.goto(new URL('/__cad/server', args.url).href);
  await page.addScriptTag({ content: bundle.outputFiles[0].text });
  const startedAt = new Date().toISOString();
  const result = await page.evaluate(options => globalThis.runPickingProbe(options), {
    dataUrl: `http://127.0.0.1:${server.address().port}`, indexType: component.indices.constructor.name, workerUrl,
  });
  const finishedAt = new Date().toISOString();
  const report = {
    startedAt, finishedAt,
    qualification: 'Isolated component in headless Chromium; current shared picking source bundled as a probe, actual production Vite worker fetched from the viewer origin. No WebGL or whole-assembly picking timing. Setup/decode/hash/reference-rays/denial/cancellation are outside the reported first-pick-to-ready window. Unsampled; long tasks are main-thread observations, not worker elapsed time.',
    browserVersion: browser.version(), cpu: os.cpus()[0].model, node: process.version,
    input: { path: path.resolve(args.tess), bytes: input.length, sha256: sha(input) },
    servedClientProof, servedWorkerProof: { url: workerUrl, bytes: workerBytes.length, sha256: sha(workerBytes), matches: true },
    probeBundleSha256: sha(bundle.outputFiles[0].contents),
    runtimeFingerprintAtStart, runtimeFingerprintAtEnd: viewerRuntimeFingerprint(), result, pageErrors,
  };
  fs.writeFileSync(args.out, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ startedAt, finishedAt, firstPickMs: result.firstPickMs, workerReadyMs: result.workerReadyAfterFirstPickMs, longTasks: result.timedWindow.longTasks, workers: result.workers, pageErrors }));
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
