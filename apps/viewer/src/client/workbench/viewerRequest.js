// Preserve request context across the artifact hook. A transport failure is not a
// compiler diagnosis; callers can explain it without guessing what the server did.
export class ViewerRequestError extends Error {
  constructor(failure, cause) {
    super(failure.detail, { cause });
    this.name = "ViewerRequestError";
    this.failure = failure;
  }
}

export function serverErrorMessage(payload) {
  const value = payload?.error || payload?.result?.error || payload?.result?.validation?.error;
  if (typeof value === "string") return value.trim();
  return String(value?.message || payload?.message || payload?.reason || "").trim();
}

export async function requestViewerJson(url, options, operation) {
  const requestUrl = typeof window !== "undefined" && window.location?.href
    ? new URL(url, window.location.href).href : url;
  const context = { operation, url: requestUrl, method: options?.method || "GET" };
  let response;
  try {
    response = await fetch(url, options);
  } catch (cause) {
    if (options?.signal?.aborted || cause?.name === "AbortError") throw cause;
    throw new ViewerRequestError({ ...context, kind: "network", detail: String(cause?.message || cause) }, cause);
  }
  let payload;
  try {
    payload = await response.json();
  } catch (cause) {
    if (options?.signal?.aborted || cause?.name === "AbortError") throw cause;
    throw new ViewerRequestError({
      ...context, kind: response.ok ? "response" : "http", status: response.status,
      detail: response.ok ? "The server returned an unreadable JSON response." : `HTTP ${response.status} ${response.statusText}`.trim()
    }, cause);
  }
  if (!response.ok) {
    throw new ViewerRequestError({
      ...context, kind: payload?.state === "failed" ? "compile" : "http", status: response.status,
      detail: serverErrorMessage(payload) || `HTTP ${response.status} ${response.statusText}`.trim()
    });
  }
  return payload;
}
