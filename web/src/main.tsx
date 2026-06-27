import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { readSsoCookie, writeSsoCookie } from "./sso";

// Cross-engine SSO handoff: resolve the tier-key from (in priority order) the
// entry URL `?key=<mao_live_…>` (e.g. arriving from the Plan2Cash "Native"
// link), the per-origin localStorage cache, then the shared parent-domain
// cookie set by a sibling *.sim-os.ai engine. Strip the URL param so the key
// never lingers in the address bar / history, then mirror whatever we resolved
// into BOTH localStorage (fast per-engine cache) and the cookie (the
// cross-subdomain carrier). Runs before the App reads localStorage, so the
// first render is authed.
try {
  const params = new URLSearchParams(window.location.search);
  let key = params.get("key") ?? "";
  if (key) {
    params.delete("key");
    const q = params.toString();
    window.history.replaceState(
      {},
      "",
      window.location.pathname + (q ? `?${q}` : "") + window.location.hash,
    );
  }
  if (!key) key = localStorage.getItem("dso_token_v1") ?? "";
  if (!key) key = readSsoCookie();
  if (key) {
    localStorage.setItem("dso_token_v1", key);
    writeSsoCookie(key);
  }
} catch {
  /* SSO resolve is best-effort; the SPA still loads */
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
