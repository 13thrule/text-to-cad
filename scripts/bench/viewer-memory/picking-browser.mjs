// Bundled by picking.mjs; no application or generated asset is modified.
import * as THREE from '../../../packages/cadgen-js/node_modules/three/build/three.module.js';
import { scheduleRuntimeRaycastBvh, builtGeometryBvhBytes } from '../../../packages/cadgen-js/src/lib/viewer/raycastBvh.js';
import { createRaycastBvhWorkerClient } from '../../../packages/cadgen-js/src/lib/viewer/raycastBvhWorkerClient.js';

const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const sha = async array => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', array)), b => b.toString(16).padStart(2, '0')).join('');
const assert = (value, message) => { if (!value) throw new Error(message); };
const sorted = hits => hits.map(hit => hit.faceIndex).sort((a, b) => a - b);

globalThis.runPickingProbe = async ({ dataUrl, indexType, workerUrl }) => {
  const [positions, indexBytes] = await Promise.all(['position', 'index'].map(async name =>
    (await fetch(`${dataUrl}/${name}`)).arrayBuffer()));
  const position = new Float32Array(positions);
  const index = indexType === 'Uint16Array' ? new Uint16Array(indexBytes) : new Uint32Array(indexBytes);
  const geometry = () => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(position, 3));
    g.setIndex(new THREE.BufferAttribute(index, 1));
    g.computeBoundingBox(); g.computeBoundingSphere();
    return g;
  };
  const g = geometry();
  const mesh = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }));
  mesh.updateMatrixWorld();
  const beforeHashes = await Promise.all([sha(position), sha(index)]);
  const center = g.boundingBox.getCenter(new THREE.Vector3());
  const distance = g.boundingBox.getSize(new THREE.Vector3()).length() * 2;
  const rays = [];
  for (let axis = 0; axis < 3; axis++) for (const sign of [-1, 1]) {
    const dir = new THREE.Vector3().setComponent(axis, sign);
    rays.push(new THREE.Raycaster(center.clone().addScaledVector(dir, -distance), dir));
  }
  const workers = { created: 0, terminated: 0 };
  const events = [];
  let cancelGeometry = null;
  const client = createRaycastBvhWorkerClient({ createWorker: () => {
    const worker = new Worker(workerUrl, { type: 'module' });
    workers.created++;
    events.push({ kind: 'worker-created', at: performance.now() });
    const terminate = worker.terminate.bind(worker);
    worker.terminate = () => { workers.terminated++; events.push({ kind: 'worker-terminated', at: performance.now() }); terminate(); };
    if (cancelGeometry) setTimeout(() => cancelGeometry.dispose(), 0);
    return worker;
  } });
  const longTasks = [];
  const observer = new PerformanceObserver(list => longTasks.push(...list.getEntries().map(e => ({ start: e.startTime, duration: e.duration }))));
  observer.observe({ type: 'longtask' });
  let reservationCount = 0;
  let finish;
  const ready = new Promise(resolve => { finish = resolve; });
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh }] }, {
    deferUntilRaycast: true, workerClient: client,
    reserveBuild: ({ estimatedBytes }) => {
      reservationCount++;
      events.push({ kind: 'reserved', at: performance.now(), estimatedBytes });
      return { ok: true, token: 'first' };
    },
    finishBuild: (token, { builtBytes }) => {
      reservationCount--;
      const event = { kind: 'finished', at: performance.now(), token, builtBytes };
      events.push(event); finish(event);
    },
  });
  await pause(100);
  assert(!g.boundsTree && workers.created === 0, 'BVH must remain absent until the first candidate ray');
  const heartbeats = [];
  const timer = setInterval(() => heartbeats.push(performance.now()), 5);
  const windowStart = performance.now();
  const firstHits = rays[0].intersectObject(mesh, false);
  const firstEnd = performance.now();
  const firstUsedStockFallback = !g.boundsTree && workers.created === 0;
  const completed = await Promise.race([ready, pause(15000).then(() => { throw new Error('Worker BVH timeout'); })]);
  const windowEnd = performance.now();
  clearInterval(timer);
  await pause(100); // Deliver the observer's final completed long task.
  observer.disconnect();
  assert(g.boundsTree && completed.builtBytes > 0, 'Actual served worker must install its BVH');
  const selectedTasks = longTasks.filter(task => task.start < windowEnd && task.start + task.duration > windowStart);
  const heartbeatGaps = [windowStart, ...heartbeats, windowEnd].slice(1).map((value, i) => value - [windowStart, ...heartbeats][i]);
  const accelerated = [], stock = [];
  for (let i = 0; i < rays.length; i++) {
    await pause(10);
    let start = performance.now();
    const fast = rays[i].intersectObject(mesh, false);
    accelerated.push({ ray: i, ms: performance.now() - start, faceIndices: sorted(fast) });
    await pause(10);
    const exact = [];
    start = performance.now();
    THREE.Mesh.prototype.raycast.call(mesh, rays[i], exact);
    stock.push({ ray: i, ms: performance.now() - start, faceIndices: sorted(exact) });
    assert(JSON.stringify(sorted(fast)) === JSON.stringify(sorted(exact)), `Ray ${i} hit multiset changed`);
  }
  assert(JSON.stringify(sorted(firstHits)) === JSON.stringify(stock[0].faceIndices), 'First fallback hit multiset changed');
  const afterHashes = await Promise.all([sha(position), sha(index)]);
  const displayArraysUnchanged = position === g.attributes.position.array && index === g.index.array && JSON.stringify(beforeHashes) === JSON.stringify(afterHashes);
  assert(displayArraysUnchanged, 'Display arrays changed or transferred away');
  const beforeDenied = { ...workers };
  const deniedGeometry = geometry();
  let deniedCount = 0;
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh: new THREE.Mesh(deniedGeometry, mesh.material) }] }, {
    workerClient: client, reserveBuild: () => ({ ok: false }), onBuildDenied: () => deniedCount++,
  });
  for (let i = 0; i < 100 && !deniedCount; i++) await pause(10);
  assert(deniedCount === 1 && !deniedGeometry.boundsTree && workers.created === beforeDenied.created, 'Denied build created worker or accelerator');
  deniedGeometry.dispose();
  cancelGeometry = geometry();
  let cancellationFinished;
  const cancelled = new Promise(resolve => { cancellationFinished = resolve; });
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh: new THREE.Mesh(cancelGeometry, mesh.material) }] }, {
    workerClient: client,
    reserveBuild: () => { reservationCount++; return { ok: true, token: 'cancel' }; },
    finishBuild: (token, { builtBytes }) => { reservationCount--; cancellationFinished({ token, builtBytes }); },
  });
  const cancellation = await Promise.race([cancelled, pause(3000).then(() => { throw new Error('Cancellation timeout'); })]);
  await pause(10);
  assert(!cancelGeometry.boundsTree && cancellation.builtBytes === 0 && reservationCount === 0 && workers.created === workers.terminated, 'Disposed worker retained resources');
  const report = {
    component: { vertices: position.length / 3, triangles: index.length / 3, copiedInputBytes: position.byteLength + index.byteLength },
    firstPickMs: firstEnd - windowStart, firstUsedStockFallback,
    firstHitFaceIndices: sorted(firstHits), workerReadyAfterFirstPickMs: completed.at - windowStart,
    timedWindow: { start: windowStart, firstEnd, end: windowEnd, longTasks: selectedTasks, heartbeatGapsMs: heartbeatGaps },
    events, accelerated, stock, bvhBytes: builtGeometryBvhBytes(g),
    displayArraysUnchanged, beforeHashes, afterHashes, hitMultisetsEqual: true,
    denied: { count: deniedCount, workerCreated: workers.created - beforeDenied.created - 1 },
    cancellation, finalReservationCount: reservationCount, workers,
  };
  g.dispose(); mesh.material.dispose();
  return report;
};
