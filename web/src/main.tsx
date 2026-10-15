import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { clearSsoCookie, readSsoCookie, writeSsoCookie } from "./sso";
import { bootSession, maoAuthBase } from "./lib/session";

const TOKEN_KEY = "dso_token_v1";

// Sign-in resolution, once per page load (P0-11 R2a, lib/session.ts).
// MAO /auth on: the HttpOnly session cookie is the sign-in. A key arriving by
// `?key=`, a legacy localStorage copy or the shared mao_sso cookie is traded
// once for the session; this page then keeps no key anywhere.
// MAO /auth off or unreachable: today's flow. Resolve `?key=` (e.g. the
// Plan2Cash "Native" link) then the shared parent-domain cookie, which is
// AUTHORITATIVE (no cookie = signed out elsewhere, drop the local copy), and
// mirror it into localStorage and the cookie.
// Either way `?key=` is stripped so the key never lingers in the address bar.
async function resolveToken(): Promise<string> {
  try {
    return await bootSession({
      base: maoAuthBase(),
      fetch: (url, init) => fetch(url, init),
      search: window.location.search,
      stripKeyParam: () => {
        const params = new URLSearchParams(window.location.search);
        params.delete("key");
        const q = params.toString();
        window.history.replaceState(
          {},
          "",
          window.location.pathname + (q ? `?${q}` : "") + window.location.hash,
        );
      },
      storage: {
        get: (k) => localStorage.getItem(k),
        set: (k, v) => localStorage.setItem(k, v),
        remove: (k) => localStorage.removeItem(k),
      },
      storageKey: TOKEN_KEY,
      readSso: readSsoCookie,
      writeSso: writeSsoCookie,
      clearSso: clearSsoCookie,
    });
  } catch {
    /* SSO resolve is best-effort; the SPA still loads */
    return "";
  }
}

resolveToken().then((token) => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App initialToken={token} />
    </StrictMode>,
  );
});
