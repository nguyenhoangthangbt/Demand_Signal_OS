// P0-11 R2a wiring: every authenticated engine call goes through authInit()
// (so a session marker becomes cookie credentials, never a header), boot runs
// through bootSession(), and sign-out revokes the MAO session.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = (f: string) => readFileSync(join(here, "../src", f), "utf8");

test("every key-bearing fetch is wrapped in authInit()", () => {
  for (const f of ["App.tsx", "BatchForecast.tsx", "LeaderboardView.tsx", "IdentityBadge.tsx"]) {
    const s = src(f);
    // each fetch( that sends a key header must be an authInit(...) call
    const calls = s.split("fetch(").slice(1);
    for (const c of calls) {
      const call = c.slice(0, 400);
      const sendsKey = /Authorization|X-API-Key|authHeaders\(/.test(call.split(");")[0]);
      if (sendsKey) assert.match(call, /authInit\(/, `${f}: fetch(${call.slice(0, 80)}...`);
    }
  }
});

test("boot goes through bootSession and the App gets the resolved token", () => {
  const m = src("main.tsx");
  assert.match(m, /bootSession\(/);
  assert.match(m, /<App initialToken=\{token\} \/>/);
  assert.doesNotMatch(m, /localStorage\.setItem\("dso_token_v1"/);
});

test("cookie mode never mirrors the token into localStorage or mao_sso", () => {
  const a = src("App.tsx");
  assert.match(a, /if \(isSessionToken\(token\)\) return;\s*\n\s*if \(token\) \{\s*\n\s*localStorage\.setItem/);
});

test("sign-out revokes the MAO session; sign-in goes through signInWithKey", () => {
  const a = src("App.tsx");
  assert.match(a, /if \(isSessionToken\(token\)\) await endSession\(\);/);
  assert.match(a, /signInWithKey\(draftToken\.trim\(\)\)/);
});

test("the leaderboard key field is never prefilled with a session marker", () => {
  const l = src("LeaderboardView.tsx");
  assert.match(l, /isSessionToken\(token\) \? "" : token \|\| readSsoCookie\(\)/);
});

test("no key ever goes into a URL", () => {
  for (const f of ["App.tsx", "BatchForecast.tsx", "LeaderboardView.tsx", "IdentityBadge.tsx", "SimosHandoffPanel.tsx"]) {
    assert.doesNotMatch(src(f), /[?&](key|token|api_key)=\$\{/, f);
  }
});
