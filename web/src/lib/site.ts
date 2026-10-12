// Which public site is serving this page.
//
// sim-os.ai is the self-serve site (Free, Pro, Premium). plan2cash.com is the
// Enterprise site. Both are served by the same container: the plan2cash.com
// edge proxy rewrites the text "sim-os.ai" to "plan2cash.com" in responses, so
// never test for "sim-os.ai" here (it would match on both sites). The literal
// "plan2cash.com" survives the rewrite. Any other host (localhost, previews)
// counts as the self-serve site.
export type Site = "simos" | "plan2cash";

export function site(
  hostname: string = typeof window !== "undefined" ? window.location.hostname : "",
): Site {
  return hostname === "plan2cash.com" || hostname.endsWith(".plan2cash.com") ? "plan2cash" : "simos";
}
