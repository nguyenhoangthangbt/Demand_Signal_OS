// P0-11 R2a: the browser holds an HttpOnly MAO session cookie instead of the
// key. These tests pin the front-end contract: probe and sign-in
// classification, no key in localStorage / mao_sso / URLs in cookie mode,
// X-Requested-With on writes, the bearer fallback when MAO /auth is off, and
// sign-out revoking the session.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  authInit,
  bootSession,
  endSession,
  establishSession,
  isSessionToken,
  maoAuthBase,
  probeSession,
  sessionMode,
  setSessionMode,
  signInWithKey,
  type BootDeps,
} from "../src/lib/session.ts";

type Call = { url: string; init: RequestInit };

function fakeFetch(routes: Record<string, number | "throw">, body: unknown = {}) {
  const calls: Call[] = [];
  const fn = async (url: string, init: RequestInit = {}) => {
    calls.push({ url, init });
    const method = (init.method ?? "GET").toUpperCase();
    const status = routes[`${method} ${url}`];
    if (status === undefined || status === "throw") throw new TypeError("network");
    return new Response(JSON.stringify(body), { status });
  };
  return { fn, calls };
}

const BASE = "https://agents-api.sim-os.ai";
const INFO = { authenticated: true, client_id: "c-1", email: "a@b.c", plan: "premium" };

test("auth base follows the site, env override wins, other hosts have none", () => {
  assert.equal(maoAuthBase("demand-signal.sim-os.ai"), "https://agents-api.sim-os.ai");
  assert.equal(maoAuthBase("sim-os.ai"), "https://agents-api.sim-os.ai");
  assert.equal(maoAuthBase("demand-signal.plan2cash.com"), "https://agents-api.plan2cash.com");
  assert.equal(maoAuthBase("plan2cash.com"), "https://agents-api.plan2cash.com");
  assert.equal(maoAuthBase("localhost"), "");
  assert.equal(maoAuthBase("localhost", "http://localhost:8763/"), "http://localhost:8763");
  assert.equal(maoAuthBase("demand-signal.sim-os.ai", "off"), "");
});

test("probe: 200 authenticated, 401 signed out, 404/503/network/no base = bearer", async () => {
  const ok = fakeFetch({ [`GET ${BASE}/auth/session`]: 200 }, INFO);
  const p = await probeSession(BASE, ok.fn);
  assert.equal(p.mode, "cookie");
  assert.equal(p.mode === "cookie" && p.authenticated, true);
  assert.equal(ok.calls[0].init.credentials, "include");

  const out = await probeSession(BASE, fakeFetch({ [`GET ${BASE}/auth/session`]: 401 }).fn);
  assert.deepEqual(out, { mode: "cookie", authenticated: false });
  for (const st of [404, 503, 500, 403] as const) {
    const r = await probeSession(BASE, fakeFetch({ [`GET ${BASE}/auth/session`]: st }).fn);
    assert.deepEqual(r, { mode: "bearer" }, `status ${st}`);
  }
  assert.deepEqual(await probeSession(BASE, fakeFetch({}).fn), { mode: "bearer" });
  const none = fakeFetch({});
  assert.deepEqual(await probeSession("", none.fn), { mode: "bearer" });
  assert.equal(none.calls.length, 0, "no base means no request");
  // 200 without authenticated:true is not a session
  const odd = await probeSession(BASE, fakeFetch({ [`GET ${BASE}/auth/session`]: 200 }, {}).fn);
  assert.deepEqual(odd, { mode: "bearer" });
});

test("establish: CSRF header + credentials; 200 ok, 401 invalid, else unavailable", async () => {
  const f = fakeFetch({ [`POST ${BASE}/auth/session`]: 200 }, INFO);
  const r = await establishSession(BASE, "mao_live_abc", f.fn);
  assert.equal(r.status, "ok");
  const init = f.calls[0].init;
  assert.equal(init.credentials, "include");
  assert.equal((init.headers as Record<string, string>)["X-Requested-With"], "mao");
  assert.equal(init.body, JSON.stringify({ key: "mao_live_abc" }));
  assert.ok(!f.calls[0].url.includes("mao_live_"), "key never in the URL");
  assert.equal((await establishSession(BASE, "x", fakeFetch({ [`POST ${BASE}/auth/session`]: 401 }).fn)).status, "invalid");
  assert.equal((await establishSession(BASE, "x", fakeFetch({ [`POST ${BASE}/auth/session`]: 404 }).fn)).status, "unavailable");
  assert.equal((await establishSession(BASE, "x", fakeFetch({}).fn)).status, "unavailable");
});

test("authInit: session token sends no key, includes credentials, CSRF header on writes only", () => {
  const tok = "session:c-1";
  assert.ok(isSessionToken(tok));
  const get = authInit(tok, { headers: { "X-API-Key": tok, Authorization: `Bearer ${tok}` } });
  const gh = get.headers as Record<string, string>;
  assert.equal(get.credentials, "include");
  assert.equal(gh["X-API-Key"], undefined);
  assert.equal(gh["Authorization"], undefined);
  assert.equal(gh["X-Requested-With"], undefined, "GET needs no CSRF header");
  const post = authInit(tok, { method: "POST", headers: { "Content-Type": "application/json" } });
  const ph = post.headers as Record<string, string>;
  assert.equal(ph["X-Requested-With"], "mao");
  assert.equal(ph["Content-Type"], "application/json");
  // bearer mode is unchanged
  const bearer = authInit("mao_live_k", { method: "POST", headers: { Authorization: "Bearer mao_live_k" } });
  assert.deepEqual(bearer, { method: "POST", headers: { Authorization: "Bearer mao_live_k" } });
  assert.equal(bearer.credentials, undefined);
});

function deps(over: Partial<BootDeps> & { fetch: BootDeps["fetch"] }) {
  const store = new Map<string, string>();
  const sso = { value: "" };
  const urls: string[] = [];
  const d: BootDeps = {
    base: BASE,
    search: "",
    stripKeyParam: () => urls.push("stripped"),
    storage: {
      get: (k) => store.get(k) ?? null,
      set: (k, v) => void store.set(k, v),
      remove: (k) => void store.delete(k),
    },
    storageKey: "dso_token_v1",
    readSso: () => sso.value,
    writeSso: (k) => (sso.value = k),
    clearSso: () => (sso.value = ""),
    ...over,
  };
  return { d, store, sso, urls };
}

test("boot, session on and signed in: no key kept anywhere, legacy local copy removed", async () => {
  const f = fakeFetch({ [`GET ${BASE}/auth/session`]: 200 }, INFO);
  const { d, store, sso } = deps({ fetch: f.fn });
  store.set("dso_token_v1", "mao_live_old");
  const token = await bootSession(d);
  assert.ok(isSessionToken(token));
  assert.ok(!token.includes("mao_live_"));
  assert.equal(store.size, 0);
  assert.equal(sso.value, "");
  assert.equal(sessionMode(), "cookie");
});

test("boot, session on and signed out: mao_sso is exchanged once, nothing written", async () => {
  const f = fakeFetch({ [`GET ${BASE}/auth/session`]: 401, [`POST ${BASE}/auth/session`]: 200 }, INFO);
  const { d, store, sso } = deps({ fetch: f.fn });
  sso.value = "mao_live_legacy";
  const token = await bootSession(d);
  assert.ok(isSessionToken(token));
  assert.equal(f.calls.filter((c) => c.init.method === "POST").length, 1);
  assert.equal(store.size, 0, "no key in localStorage");
  // R2a keeps a valid legacy mao_sso for old tabs; MAO clears it at R2b.
  assert.equal(sso.value, "mao_live_legacy");
});

test("boot, session on: ?key= is exchanged and stripped from the URL", async () => {
  const f = fakeFetch({ [`GET ${BASE}/auth/session`]: 401, [`POST ${BASE}/auth/session`]: 200 }, INFO);
  const { d, store, urls } = deps({ fetch: f.fn, search: "?key=mao_live_url&x=1" });
  const token = await bootSession(d);
  assert.ok(isSessionToken(token));
  assert.deepEqual(urls, ["stripped"]);
  assert.equal(f.calls[1].init.body, JSON.stringify({ key: "mao_live_url" }));
  assert.equal(store.size, 0);
});

test("boot, session on: a dead key signs out and clears every copy", async () => {
  const f = fakeFetch({ [`GET ${BASE}/auth/session`]: 401, [`POST ${BASE}/auth/session`]: 401 }, INFO);
  const { d, store, sso } = deps({ fetch: f.fn });
  store.set("dso_token_v1", "mao_live_dead");
  sso.value = "mao_live_dead";
  assert.equal(await bootSession(d), "");
  assert.equal(store.size, 0);
  assert.equal(sso.value, "");
});

test("probe and boot, /auth off (200 enabled:false): bearer, the same as a 404", async () => {
  const f = fakeFetch({ [`GET ${BASE}/auth/session`]: 200 }, { enabled: false, authenticated: false });
  assert.deepEqual(await probeSession(BASE, f.fn), { mode: "bearer" });
  const g = deps({ fetch: f.fn });
  g.sso.value = "mao_live_k";
  assert.equal(await bootSession(g.d), "mao_live_k");
  assert.equal(g.store.get("dso_token_v1"), "mao_live_k");
  assert.equal(sessionMode(), "bearer");
  assert.ok(f.calls.every((c) => (c.init.method ?? "GET").toUpperCase() === "GET"), "no sign-in POST");
});

test("boot, /auth off (404): today's bearer flow, key adopted from mao_sso", async () => {
  const f = fakeFetch({ [`GET ${BASE}/auth/session`]: 404 });
  const { d, store, sso } = deps({ fetch: f.fn });
  sso.value = "mao_live_k";
  assert.equal(await bootSession(d), "mao_live_k");
  assert.equal(store.get("dso_token_v1"), "mao_live_k");
  assert.equal(sessionMode(), "bearer");
  // and with no cookie, a stale local copy is dropped (cookie is authoritative)
  const g = deps({ fetch: f.fn });
  g.store.set("dso_token_v1", "mao_live_stale");
  assert.equal(await bootSession(g.d), "");
  assert.equal(g.store.size, 0);
});

test("sign-in: cookie mode stores nothing; invalid surfaces; bearer mode keeps the key", async () => {
  setSessionMode("cookie");
  const ok = await signInWithKey("mao_live_new", BASE, fakeFetch({ [`POST ${BASE}/auth/session`]: 200 }, INFO).fn);
  assert.ok("token" in ok && isSessionToken(ok.token));
  const bad = await signInWithKey("mao_live_bad", BASE, fakeFetch({ [`POST ${BASE}/auth/session`]: 401 }).fn);
  assert.deepEqual(bad, { error: "invalid" });
  const off = await signInWithKey("mao_live_k", BASE, fakeFetch({ [`POST ${BASE}/auth/session`]: 404 }).fn);
  assert.deepEqual(off, { token: "mao_live_k" });
  assert.equal(sessionMode(), "bearer");
  const f = fakeFetch({});
  assert.deepEqual(await signInWithKey("mao_live_k", BASE, f.fn), { token: "mao_live_k" });
  assert.equal(f.calls.length, 0, "bearer mode does not call MAO");
});

test("sign-out revokes the session at MAO with the CSRF header, and never throws", async () => {
  const f = fakeFetch({ [`POST ${BASE}/auth/logout`]: 200 });
  await endSession(BASE, f.fn);
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].init.credentials, "include");
  assert.equal((f.calls[0].init.headers as Record<string, string>)["X-Requested-With"], "mao");
  await endSession(BASE, fakeFetch({}).fn); // network error swallowed
  await endSession("", fakeFetch({}).fn);
});
