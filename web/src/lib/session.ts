// Browser session for the engine mesh (P0-11 R2a, design
// platforms_os docs_v1/design/P0_11_SESSION_COOKIE_DESIGN.md).
//
// MAO (agents-api) swaps the customer's mao_live_ key for an HttpOnly cookie
// (__Secure-mao_session) that page script cannot read. When that feature is on
// this page keeps NO key: not in localStorage, not in the readable mao_sso
// cookie, not in a URL. Engine calls send the cookie (credentials: include)
// and X-Requested-With: mao on writes (the engines' CSRF rule).
//
// When MAO /auth is off (MAO_SESSION_SEAL_KEY unset: GET /auth/session
// answers 200 {"enabled": false}, an older MAO answered 404) or
// unreachable, everything falls back to today's bearer flow. The probe at
// boot decides at runtime; there is no build-time switch.
//
// In cookie mode the App's `token` is a non-secret marker "session:<client>"
// so the existing "signed in?" checks keep working; authInit() turns it into
// cookie credentials and never sends it as a header.

export type SessionInfo = {
  authenticated?: boolean;
  client_id?: string;
  email?: string | null;
  display_name?: string | null;
  plan?: string | null;
  role?: string | null;
  is_admin?: boolean;
};

export type SessionProbe =
  | { mode: "cookie"; authenticated: true; info: SessionInfo }
  | { mode: "cookie"; authenticated: false }
  | { mode: "bearer" };

export type EstablishResult =
  | { status: "ok"; info: SessionInfo }
  | { status: "invalid" }
  | { status: "unavailable" };

type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

export const SESSION_TOKEN_PREFIX = "session:";
const CSRF_HEADER = "X-Requested-With";
const CSRF_VALUE = "mao";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

let mode: "bearer" | "cookie" = "bearer";

/** 'cookie' once MAO answered /auth/session; 'bearer' until then and when off. */
export function sessionMode(): "bearer" | "cookie" {
  return mode;
}

export function setSessionMode(m: "bearer" | "cookie"): void {
  mode = m;
}

function envAuthBase(): string | undefined {
  try {
    return import.meta.env.VITE_MAO_AUTH_BASE;
  } catch {
    return undefined; // node test runner: no import.meta.env
  }
}

/** MAO base for /auth/*: env override, else by site. plan2cash.com is tested
 *  by its own literal (the edge rewrites the text "sim-os.ai"). '' = none. */
export function maoAuthBase(
  hostname: string = typeof window !== "undefined" ? window.location.hostname : "",
  envBase: string | undefined = envAuthBase(),
): string {
  const env = (envBase ?? "").trim();
  if (env) return env === "off" ? "" : env.replace(/\/+$/, "");
  if (hostname === "plan2cash.com" || hostname.endsWith(".plan2cash.com")) {
    return "https://agents-api.plan2cash.com";
  }
  if (hostname === "sim-os.ai" || hostname.endsWith(".sim-os.ai")) {
    return "https://agents-api.sim-os.ai";
  }
  return "";
}

const defaultFetch: FetchLike = (url, init) => fetch(url, init);

export function isSessionToken(token: string | null | undefined): boolean {
  return !!token && token.startsWith(SESSION_TOKEN_PREFIX);
}

export function sessionToken(info: SessionInfo): string {
  return SESSION_TOKEN_PREFIX + (info.client_id || "signed-in");
}

/** GET /auth/session: who am I, and is the feature on at all. */
export async function probeSession(
  base: string = maoAuthBase(),
  fetchImpl: FetchLike = defaultFetch,
  timeoutMs = 5000,
): Promise<SessionProbe> {
  if (!base) return { mode: "bearer" };
  const ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
  const timer = ctrl ? setTimeout(() => ctrl.abort(), timeoutMs) : null;
  try {
    const r = await fetchImpl(`${base}/auth/session`, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      signal: ctrl?.signal,
    });
    if (r.status === 401) return { mode: "cookie", authenticated: false };
    if (r.status === 200) {
      const info = (await r.json().catch(() => ({}))) as SessionInfo;
      if (info && info.authenticated === true) return { mode: "cookie", authenticated: true, info };
    }
    return { mode: "bearer" };
  } catch {
    return { mode: "bearer" };
  } finally {
    if (timer) clearTimeout(timer);
  }
}

/** POST /auth/session: trade a key (or the legacy mao_sso cookie) for the
 *  HttpOnly session cookie. The key travels in the body, never the URL. */
export async function establishSession(
  base: string = maoAuthBase(),
  key?: string,
  fetchImpl: FetchLike = defaultFetch,
): Promise<EstablishResult> {
  if (!base) return { status: "unavailable" };
  try {
    const r = await fetchImpl(`${base}/auth/session`, {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers: { "Content-Type": "application/json", [CSRF_HEADER]: CSRF_VALUE },
      body: JSON.stringify(key ? { key } : {}),
    });
    if (r.status === 200) {
      const info = (await r.json().catch(() => ({}))) as SessionInfo;
      return { status: "ok", info: info ?? {} };
    }
    if (r.status === 401) return { status: "invalid" };
    return { status: "unavailable" };
  } catch {
    return { status: "unavailable" };
  }
}

/** POST /auth/logout: MAO revokes the session and clears both cookies. */
export async function endSession(
  base: string = maoAuthBase(),
  fetchImpl: FetchLike = defaultFetch,
): Promise<void> {
  if (!base) return;
  try {
    await fetchImpl(`${base}/auth/logout`, {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers: { [CSRF_HEADER]: CSRF_VALUE },
    });
  } catch {
    /* best effort: local state is cleared regardless */
  }
}

/** Request options for an engine call made with `token`. A session marker
 *  sends no key header, includes credentials and adds the CSRF header on
 *  writes. A real key (bearer mode) leaves `init` exactly as it was. */
export function authInit(token: string | null | undefined, init: RequestInit = {}): RequestInit {
  if (!isSessionToken(token)) return init;
  const headers: Record<string, string> = {};
  const src = init.headers;
  if (src) {
    const entries: [string, string][] =
      src instanceof Headers
        ? Array.from(src.entries())
        : Array.isArray(src)
          ? (src as [string, string][])
          : Object.entries(src as Record<string, string>);
    for (const [k, v] of entries) {
      const lk = k.toLowerCase();
      if (lk === "authorization" || lk === "x-api-key") continue;
      headers[k] = v;
    }
  }
  if (UNSAFE.has((init.method ?? "GET").toUpperCase())) headers[CSRF_HEADER] = CSRF_VALUE;
  return { ...init, headers, credentials: "include" };
}

export interface BootDeps {
  base: string;
  fetch: FetchLike;
  /** window.location.search */
  search: string;
  /** remove ?key= from the address bar */
  stripKeyParam: () => void;
  storage: { get(k: string): string | null; set(k: string, v: string): void; remove(k: string): void };
  storageKey: string;
  readSso: () => string;
  writeSso: (key: string) => void;
  clearSso: () => void;
}

/** Today's flow: ?key= then the shared mao_sso cookie, mirrored into
 *  localStorage and the cookie; nothing found drops the stale local copy. */
function bearerResolve(d: BootDeps, urlKey: string): string {
  const key = urlKey || d.readSso();
  if (key) {
    d.storage.set(d.storageKey, key);
    d.writeSso(key);
  } else {
    d.storage.remove(d.storageKey);
  }
  return key;
}

/** Resolve the signed-in state once per page load. Returns the App token:
 *  a session marker (cookie mode), a key (bearer mode) or '' (signed out). */
export async function bootSession(d: BootDeps): Promise<string> {
  let urlKey = "";
  try {
    urlKey = new URLSearchParams(d.search).get("key") ?? "";
  } catch {
    urlKey = "";
  }
  if (urlKey) d.stripKeyParam();

  const probe = await probeSession(d.base, d.fetch);
  if (probe.mode === "bearer") {
    setSessionMode("bearer");
    return bearerResolve(d, urlKey);
  }
  setSessionMode("cookie");

  if (probe.authenticated) {
    d.storage.remove(d.storageKey);
    if (urlKey) {
      const switched = await establishSession(d.base, urlKey, d.fetch);
      if (switched.status === "ok") return sessionToken(switched.info);
    }
    return sessionToken(probe.info);
  }

  const candidate = urlKey || d.storage.get(d.storageKey) || d.readSso();
  if (!candidate) return "";
  const est = await establishSession(d.base, candidate, d.fetch);
  if (est.status === "ok") {
    d.storage.remove(d.storageKey);
    return sessionToken(est.info);
  }
  if (est.status === "invalid") {
    d.storage.remove(d.storageKey);
    d.clearSso();
    return "";
  }
  setSessionMode("bearer");
  return bearerResolve(d, urlKey);
}

/** Sign in with a typed key. Cookie mode stores nothing and returns a session
 *  marker; a rejected key is reported; MAO unavailable falls back to bearer. */
export async function signInWithKey(
  key: string,
  base: string = maoAuthBase(),
  fetchImpl: FetchLike = defaultFetch,
): Promise<{ token: string } | { error: "invalid" }> {
  if (sessionMode() !== "cookie") return { token: key };
  const est = await establishSession(base, key, fetchImpl);
  if (est.status === "ok") return { token: sessionToken(est.info) };
  if (est.status === "invalid") return { error: "invalid" };
  setSessionMode("bearer");
  return { token: key };
}
