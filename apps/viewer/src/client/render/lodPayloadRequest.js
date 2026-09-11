import { surfTessellationCacheKey } from "cadgen-js/lib/renderAssetClient.js";
import { lodTessellationForLevel } from "cadgen-js/lib/surf/lodPolicy.js";

export function lodPayloadRequest(component, level) {
  return Object.freeze({ descriptor: component.descriptor, file: component.file,
    cid: component.cid, identity: component.identity, url: component.surfUrl,
    key: surfTessellationCacheKey(component.surfUrl, lodTessellationForLevel(level), component.identity) });
}

export function matchesLodPayloadRequest(request, context, cid, level, url) {
  const identity = context?.descriptor?.components?.[cid];
  return !!request && request.descriptor === context?.descriptor && request.file === context?.file &&
    request.cid === cid && request.identity === identity && request.url === url &&
    request.key === surfTessellationCacheKey(url, lodTessellationForLevel(level), identity);
}
