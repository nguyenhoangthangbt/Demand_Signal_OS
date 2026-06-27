// Cross-subdomain single sign-on for the *.sim-os.ai engine mesh.
//
// localStorage is per-origin, so a key saved on one engine's subdomain is
// invisible to the others. To make "log in once, every granted engine is
// already logged in" work, we ALSO mirror the key into a cookie on the parent
// domain `.sim-os.ai`, which every *.sim-os.ai engine reads on boot.
// localStorage stays the fast per-engine cache; the cookie is the carrier.
// (A cookie, unlike ?key= in a URL, never lands in browser history, server
// access logs, or Referer headers.) On a non-sim-os.ai host (local dev) it
// degrades to a host-only cookie so dev keeps working.

const SSO_COOKIE = "mao_sso";
const MAX_AGE_SECONDS = 60 * 60 * 24 * 30; // 30d; the server 401 is the real expiry

function domainAttr(): string {
  try {
    return window.location.hostname.endsWith("sim-os.ai") ? "; domain=.sim-os.ai" : "";
  } catch {
    return "";
  }
}

/** Read the shared SSO key from the parent-domain cookie ("" if absent). */
export function readSsoCookie(): string {
  try {
    const m = document.cookie.match(/(?:^|;\s*)mao_sso=([^;]*)/);
    return m ? decodeURIComponent(m[1]) : "";
  } catch {
    return "";
  }
}

/** Mirror the key into the shared cookie so sibling engines auto-authenticate. */
export function writeSsoCookie(key: string): void {
  if (!key) return;
  try {
    const secure = window.location.protocol === "https:" ? "; Secure" : "";
    document.cookie =
      `${SSO_COOKIE}=${encodeURIComponent(key)}; path=/${domainAttr()}` +
      `; max-age=${MAX_AGE_SECONDS}; SameSite=Lax${secure}`;
  } catch {
    /* cookies unavailable — the per-origin localStorage cache still works */
  }
}

/** Clear the shared cookie (logout / expired key). */
export function clearSsoCookie(): void {
  try {
    document.cookie = `${SSO_COOKIE}=; path=/${domainAttr()}; max-age=0; SameSite=Lax`;
  } catch {
    /* ignore */
  }
}
