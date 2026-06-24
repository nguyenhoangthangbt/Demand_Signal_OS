import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

// Cross-engine SSO handoff: capture `?key=<mao_live_…>` from the entry URL
// (e.g. arriving from the Plan2Cash "Native" link), persist it as the token,
// and strip the param so the key never lingers in the address bar / history.
// Runs before the App reads localStorage, so the first render is authed.
try {
  const params = new URLSearchParams(window.location.search);
  const ssoKey = params.get("key");
  if (ssoKey) {
    localStorage.setItem("dso_token_v1", ssoKey);
    params.delete("key");
    const q = params.toString();
    window.history.replaceState(
      {},
      "",
      window.location.pathname + (q ? `?${q}` : "") + window.location.hash,
    );
  }
} catch {
  /* localStorage / history unavailable — SPA still loads, just no auto-key */
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
