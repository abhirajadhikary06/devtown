export class ApiError extends Error { constructor(public status: number, msg: string) { super(msg); } }

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch("/api" + path, { credentials: "include", headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : msg; } catch { /* ignore */ }
    throw new ApiError(r.status, msg);
  }
  return r.json();
}
export const post = <T,>(p: string, body?: unknown) => api<T>(p, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
