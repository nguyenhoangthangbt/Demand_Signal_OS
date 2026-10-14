// Search and sharing hygiene for demand-signal.sim-os.ai and
// demand-signal.plan2cash.com (customer-journey audit 2026-10-12, theme 2.12:
// D-22, D-23, E-15). Runs on Node's built-in test runner: `npm test`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const webDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p: string) => readFileSync(join(webDir, p), "utf8");
const conf = read("nginx.conf");
const index = read("index.html");

// The only public, indexable URL: the page is hash-routed (#leaderboard, ...).
const SITEMAP_ALLOWLIST = new Set(["https://demand-signal.sim-os.ai/"]);

test("robots.txt is a real robots file naming this host's sitemap (D-22)", () => {
  const robots = read("public/robots.txt");
  assert.ok(!/<html/i.test(robots));
  assert.match(robots, /^User-agent: \*$/m);
  assert.match(robots, /^Disallow: \/api\/$/m);
  assert.match(robots, /^Sitemap: https:\/\/demand-signal\.sim-os\.ai\/sitemap\.xml$/m);
});

test("sitemap.xml lists only allowlisted public URLs, no fragments (D-22)", () => {
  const sitemap = read("public/sitemap.xml");
  assert.ok(sitemap.startsWith('<?xml version="1.0" encoding="UTF-8"?>'));
  const locs = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
  assert.ok(locs.length > 0);
  for (const loc of locs) {
    assert.ok(SITEMAP_ALLOWLIST.has(loc), `sitemap lists ${loc}`);
    assert.ok(!loc.includes("#"));
  }
});

test("favicons are real images and the head declares them (D-22)", () => {
  const ico = readFileSync(join(webDir, "public/favicon.ico"));
  assert.deepEqual([...ico.subarray(0, 4)], [0, 0, 1, 0], "favicon.ico is not an ICO file");
  assert.ok(ico.readUInt16LE(4) >= 3, "favicon.ico carries 16, 32 and 48 px images");
  assert.match(read("public/favicon.svg"), /^<svg /);
  assert.ok(index.includes('<link rel="icon" type="image/svg+xml" href="/favicon.svg" />'));
  assert.ok(index.includes('<link rel="alternate icon" href="/favicon.ico" />'));
});

test("unknown paths get a real 404 page, not the app (D-23)", () => {
  assert.ok(existsSync(join(webDir, "public/404.html")));
  const notFound = read("public/404.html");
  assert.ok(notFound.includes('<meta name="robots" content="noindex" />'));
  assert.ok(notFound.includes("Page not found"));
  assert.ok(notFound.includes('href="/"'));
  assert.ok(!/[—·]/.test(notFound), "em-dash or middle dot in the 404 page");
  const catchAll = conf.match(/location \/ \{([^}]*)\}/);
  assert.ok(catchAll, "no catch-all location");
  assert.match(catchAll[1], /try_files \$uri \$uri\/ =404;/);
  assert.ok(!/index\.html/.test(catchAll[1]), "catch-all still falls back to the app");
  assert.match(conf, /error_page 404 \/404\.html;/);
  assert.match(conf, /location = \/404\.html \{\s*internal;/);
});

test("plan2cash.com gets the Plan2Cash title suffix, sim-os.ai none (E-15)", () => {
  assert.match(conf, /map \$http_x_site \$title_sfx \{\s*default\s+"";\s*plan2cash\s+" \| Plan2Cash";\s*\}/);
  const title = index.match(/<title>([^<]+)<\/title>/);
  assert.ok(title);
  // Both the <title> and og:title are rewritten in the served index only.
  assert.ok(conf.includes(`sub_filter '<title>${title[1]}</title>' '<title>${title[1]}$title_sfx</title>';`));
  const og = `<meta property="og:title" content="${title[1]}" />`;
  assert.ok(index.includes(og), "og:title no longer matches the title");
  assert.ok(conf.includes(`sub_filter '${og}' '<meta property="og:title" content="${title[1]}$title_sfx" />';`));
  const indexLoc = conf.match(/location = \/index\.html \{([^}]*)\}/);
  assert.ok(indexLoc && /sub_filter/.test(indexLoc[1]), "the served index carries the sub_filter");
});
