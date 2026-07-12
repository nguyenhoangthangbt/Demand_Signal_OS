"""DemandSignalOS doctor — deterministic robustness probe.

DSO at v0.1 is a Python library consumed by PlanningOS + SimOS, plus a
web SPA at demand-signal.sim-os.ai. No standalone API yet (v0.1.5 API
extraction reserved per memory). The doctor probes both the library
surface and the public web SPA.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
from pathlib import Path

PLATFORM = "demand_signal"
LABEL = "DemandSignalOS"
PUBLIC_URL = "https://demand-signal.sim-os.ai"
API_URL = "https://demand-signal-api.sim-os.ai"  # full API live since 2026-06-14


def _curl_once(url: str, timeout: int) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["curl", "-s", "-L", "--compressed", "-w", "\n%{http_code}",
             "-o", "-", "--max-time", str(timeout), url],
            capture_output=True, text=True,
            # Decode as UTF-8 with replacement: the minified JS bundle carries
            # bytes that the Windows default (cp1252) cannot decode, which would
            # crash the reader thread and leave stdout=None -> the check raised
            # AttributeError and went RED despite a healthy product.
            encoding="utf-8", errors="replace",
            timeout=timeout + 5,
        )
        body = proc.stdout
        nl = body.rfind("\n")
        if nl >= 0 and body[nl + 1:].strip().isdigit():
            return int(body[nl + 1:].strip()), body[:nl]
        return 0, body
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return 0, str(e)


def _run_curl(url: str, timeout: int, retries: int = 1) -> tuple[int, str]:
    # Retry once on a TRANSIENT failure — status 0 (timeout / connection error)
    # or a 5xx. Under the orchestrator's parallel run (3 pytest suites + live
    # HTTP probes hammering one host at once), a healthy surface can briefly
    # time out and flake a check to RED (observed 2026-06-29: customer_surface
    # RED in parallel, GREEN standalone). One retry removes that false-RED
    # WITHOUT masking a real outage: a persistent 0/5xx still returns after the
    # retry, so the check stays RED. Real codes (200/401/...) return immediately.
    code, body = _curl_once(url, timeout)
    for _ in range(max(0, retries)):
        if code != 0 and not (500 <= code < 600):
            break
        time.sleep(1.5)
        code, body = _curl_once(url, timeout)
    return code, body


def _git_sha(repo_root: Path) -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=repo_root, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def check_code_drift(timeout: int, repo_root: Path) -> dict:
    main_sha = _git_sha(repo_root)
    if not main_sha:
        return {"name": "code_drift", "status": "RED",
                "reason": "could not read git SHA from repo root",
                "evidence": {"repo_root": str(repo_root)}}
    # Library has no deployed version to compare against; report main SHA only.
    return {"name": "code_drift", "status": "GREEN",
            "reason": f"library mode; main SHA={main_sha} (no deployed version to drift from)",
            "evidence": {"main_sha": main_sha}}


def check_container_health(timeout: int, repo_root: Path) -> dict:
    try:
        proc = subprocess.run(
            ["wsl", "-e", "bash", "-c",
             "docker ps --filter name=demand-signal-web --format '{{.Names}}\\t{{.Status}}'"],
            capture_output=True, text=True, timeout=timeout,
        )
        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        if not lines:
            return {"name": "container_health", "status": "RED",
                    "reason": "demand-signal-web container not running",
                    "evidence": None,
                    "reproducer": "wsl -e bash -c 'docker ps | grep demand-signal'"}
        return {"name": "container_health", "status": "GREEN",
                "reason": lines[0], "evidence": {"line": lines[0]}}
    except Exception as e:
        return {"name": "container_health", "status": "RED",
                "reason": f"docker probe raised: {type(e).__name__}: {e}",
                "evidence": None}


def check_api_surface(timeout: int, repo_root: Path) -> dict:
    """Two layers: (1) library import surface, (2) the LIVE forecast API.

    The full API (trust gate + forecaster leaderboard) went live 2026-06-14 at
    API_URL. We verify the library imports clean AND that the deployed API is
    healthy and the compute-heavy leaderboard route is auth-gated (401 without
    a key proves both that the route exists and that DSO_API_KEYS is set).
    """
    try:
        proc = subprocess.run(
            ["python", "-c",
             "from demand_signal_os.calibration.calibrator import DemandSignalCalibrator; "
             "from demand_signal_os.forecasting.ets import ETSMethod; "
             "from demand_signal_os.leaderboard import orchestrate; "
             "from demand_signal_os import accuracy; "
             "print('OK')"],
            cwd=repo_root, capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0 or "OK" not in proc.stdout:
            return {"name": "api_surface", "status": "RED",
                    "reason": "library import failed",
                    "evidence": {"stderr": proc.stderr[:300]},
                    "reproducer": (
                        "python -c 'from demand_signal_os.leaderboard import orchestrate'"
                    )}
    except Exception as e:
        return {"name": "api_surface", "status": "RED",
                "reason": f"import probe raised: {type(e).__name__}: {e}",
                "evidence": None}

    # Live deployed API: health + gated leaderboard route.
    health_code, _ = _run_curl(f"{API_URL}/api/v1/health", timeout)
    if health_code != 200:
        return {"name": "api_surface", "status": "RED",
                "reason": f"{API_URL}/api/v1/health returned HTTP {health_code}",
                "evidence": {"library": "ok", "api_health": health_code},
                "reproducer": f"curl -s {API_URL}/api/v1/health"}
    gate_code, _ = _run_curl(f"{API_URL}/api/v1/forecast/leaderboard/lb_probe", timeout)
    if gate_code != 401:
        return {"name": "api_surface", "status": "RED",
                "reason": (
                    f"leaderboard route returned HTTP {gate_code} without a key "
                    "(expected 401 — route missing or DSO_API_KEYS unset/open)"
                ),
                "evidence": {"library": "ok", "api_health": 200, "gate": gate_code},
                "reproducer": (
                    f"curl -s -o /dev/null -w '%{{http_code}}' "
                    f"{API_URL}/api/v1/forecast/leaderboard/lb_probe"
                )}
    return {"name": "api_surface", "status": "GREEN",
            "reason": "library imports clean + live API healthy + leaderboard gated (401)",
            "evidence": {"surface": "library+http", "api_health": 200, "gate": 401}}


def check_persistence(timeout: int, repo_root: Path) -> dict:
    """DSO at v0.1 is a stateless forecasting library — it has no DB, session,
    or durable store (no create_engine / DATABASE_URL anywhere in src). The
    persistence check therefore does not apply; SKIP it rather than flag AMBER,
    which would imply an unverified-but-expected backing that does not exist."""
    return {"name": "persistence", "status": "SKIP",
            "reason": "v0.1 is a stateless library — no persistence layer (N/A)",
            "evidence": {"version": "v0.1", "stateless": True}}


def check_customer_surface(timeout: int, repo_root: Path) -> dict:
    status, body = _run_curl(PUBLIC_URL + "/", timeout)
    if status != 200:
        return {"name": "customer_surface", "status": "RED",
                "reason": f"{PUBLIC_URL}/ returned HTTP {status}",
                "evidence": body[:200],
                "reproducer": f"curl -s {PUBLIC_URL}/"}
    if "DemandSignalOS" not in body and "Forecast" not in body:
        return {"name": "customer_surface", "status": "RED",
                "reason": "page body missing expected DSO markers",
                "evidence": body[:300]}
    # Assert the LEADERBOARD build is actually deployed: the SPA is client
    # rendered, so we fetch the main JS bundle and confirm it carries the
    # baked leaderboard API base. A page that lacks it is a stale (pre-
    # leaderboard) build even though the shell renders.
    m = re.search(r"/assets/index-[A-Za-z0-9_-]+\.js", body)
    if not m:
        return {"name": "customer_surface", "status": "RED",
                "reason": "could not locate main JS asset in index.html",
                "evidence": body[:300]}
    _, js = _run_curl(PUBLIC_URL + m.group(0), timeout)
    if "demand-signal-api.sim-os.ai/api/v1" not in js:
        return {"name": "customer_surface", "status": "RED",
                "reason": (
                    "deployed SPA bundle lacks the leaderboard API base — "
                    "stale build without the leaderboard workbench wired"
                ),
                "evidence": {"asset": m.group(0)},
                "reproducer": f"curl -s {PUBLIC_URL}{m.group(0)} | grep demand-signal-api"}
    return {"name": "customer_surface", "status": "GREEN",
            "reason": f"{PUBLIC_URL}/ serves DSO SPA with leaderboard wired to the live API",
            "evidence": {"url": PUBLIC_URL, "asset": m.group(0)}}


def check_smoke_test(timeout: int, repo_root: Path) -> dict:
    """Verify ETSMethod can be instantiated and exposes the fit_predict
    contract. We don't run a full forecast here because the
    ``ForecastRequest`` construction has many required fields; the
    e2e_baseline check (which runs pytest) covers the full forecast
    path end-to-end.
    """
    try:
        proc = subprocess.run(
            ["python", "-c",
             "from demand_signal_os.forecasting.ets import ETSMethod; "
             "m = ETSMethod(season_length=4); "
             "assert hasattr(m, 'fit_predict'), 'missing fit_predict'; "
             "assert m.method_id == 'ets', f'unexpected method_id: {m.method_id}'; "
             "print('OK')"],
            cwd=repo_root, capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0 or "OK" not in proc.stdout:
            return {"name": "smoke_test", "status": "RED",
                    "reason": "ETSMethod smoke failed",
                    "evidence": {"stderr": proc.stderr[:300], "stdout": proc.stdout[:300]},
                    "reproducer": "see check_smoke_test in scripts/doctor.py"}
        return {"name": "smoke_test", "status": "GREEN",
                "reason": "ETSMethod instantiates with fit_predict contract intact",
                "evidence": {"smoke": "ets_instantiate"}}
    except Exception as e:
        return {"name": "smoke_test", "status": "RED",
                "reason": f"smoke raised: {type(e).__name__}: {e}",
                "evidence": None}


def check_tests(timeout: int, repo_root: Path) -> dict:
    if not (repo_root / "tests").exists():
        return {"name": "tests", "status": "RED",
                "reason": "no tests/ directory", "evidence": None}
    start = time.monotonic()
    try:
        proc = subprocess.run(
            ["python", "-m", "pytest", "-q", "--tb=line", "--no-header"],
            cwd=repo_root, capture_output=True, text=True, timeout=900,
        )
        elapsed = time.monotonic() - start
        output = (proc.stdout + proc.stderr)[-3500:]
    except subprocess.TimeoutExpired:
        return {"name": "tests", "status": "RED",
                "reason": "pytest exceeded 15-minute cap", "evidence": None}
    summary = next((l.strip() for l in output.splitlines()[::-1]
                    if "passed" in l or "failed" in l), "")
    if proc.returncode == 0:
        return {"name": "tests", "status": "GREEN",
                "reason": f"{summary} (elapsed {elapsed:.1f}s)",
                "evidence": {"returncode": 0, "elapsed": elapsed}}
    return {"name": "tests", "status": "RED",
            "reason": f"pytest exit {proc.returncode}: {summary}",
            "evidence": {"returncode": proc.returncode, "tail": output[-1200:]}}


def check_e2e_baseline(timeout: int, repo_root: Path) -> dict:
    """Canonical baseline: deterministic ETS forecast on a fixed series.

    Determinism enforced by the test asserting exact output values for
    given inputs. Drift here means a non-deterministic component has
    crept into the forecast pipeline.
    """
    candidates = [
        repo_root / "tests" / "calibration" / "test_calibrator.py",
        repo_root / "tests" / "forecasting" / "test_ets.py",
    ]
    target = next((p for p in candidates if p.exists()), None)
    if target is None:
        return {"name": "e2e_baseline", "status": "AMBER",
                "reason": "no designated baseline test found",
                "evidence": {"checked": [str(p) for p in candidates]}}
    try:
        proc = subprocess.run(
            ["python", "-m", "pytest", str(target), "-v", "--tb=short"],
            cwd=repo_root, capture_output=True, text=True, timeout=180,
        )
        output = (proc.stdout + proc.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        return {"name": "e2e_baseline", "status": "RED",
                "reason": "baseline test exceeded 3-min cap",
                "evidence": None}
    if proc.returncode == 0:
        summary = next((l.strip() for l in output.splitlines()[::-1] if "passed" in l), "")
        return {"name": "e2e_baseline", "status": "GREEN",
                "reason": f"baseline deterministic: {summary}",
                "evidence": {"returncode": 0, "target": str(target.relative_to(repo_root))}}
    return {"name": "e2e_baseline", "status": "RED",
            "reason": f"baseline DRIFTED (pytest exit {proc.returncode})",
            "evidence": {"returncode": proc.returncode, "tail": output}}


def check_results_export(timeout: int, repo_root: Path) -> dict:
    """The forecast results-export .xlsx endpoint must be LIVE.

    POSTs a tiny fixed series to ``/api/v1/forecast/single.xlsx`` and asserts a
    200 + spreadsheet content-type, proving the deployed API can hand the user
    their forecast as a native Excel workbook for offline validation. A 404 means
    the results-export endpoint is not deployed (stale image)."""
    body = '{"history":[10,12,9,11,13,10,12,11],"horizon":4,"season_length":4}'
    try:
        proc = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}\t%{content_type}",
             "-X", "POST", "-H", "Content-Type: application/json", "-d", body,
             "--max-time", str(timeout), f"{API_URL}/api/v1/forecast/single.xlsx"],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        code_str, _, ctype = proc.stdout.partition("\t")
        code = int(code_str) if code_str.strip().isdigit() else 0
    except Exception as e:
        return {"name": "results_export", "status": "RED",
                "reason": f"probe raised: {type(e).__name__}: {e}", "evidence": None}
    if code == 200 and "spreadsheet" in ctype:
        return {"name": "results_export", "status": "GREEN",
                "reason": "forecast .xlsx export live (200 + spreadsheet content-type)",
                "evidence": {"code": 200, "content_type": ctype}}
    return {"name": "results_export", "status": "RED",
            "reason": (f"/forecast/single.xlsx returned HTTP {code} ({ctype or 'no ctype'}) "
                       "— results-export endpoint missing or not deployed"),
            "evidence": {"code": code, "content_type": ctype},
            "reproducer": (f"curl -s -X POST -H 'Content-Type: application/json' "
                           f"-d '{body}' {API_URL}/api/v1/forecast/single.xlsx")}


CHECKS = [check_code_drift, check_container_health, check_api_surface,
          check_persistence, check_customer_surface, check_smoke_test,
          check_results_export, check_tests, check_e2e_baseline]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--no-tests", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    checks_to_run = CHECKS
    if args.no_tests:
        checks_to_run = [c for c in CHECKS if c not in (check_tests, check_e2e_baseline)]

    results = []
    for fn in checks_to_run:
        try:
            results.append(fn(args.timeout, repo_root))
        except Exception as e:
            results.append({"name": fn.__name__.removeprefix("check_"),
                            "status": "RED",
                            "reason": f"check raised: {type(e).__name__}: {e}"})

    counts = {"GREEN": 0, "AMBER": 0, "RED": 0, "SKIP": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    verdict = "RED" if counts["RED"] else ("AMBER" if counts["AMBER"] else "GREEN")
    failed = counts["RED"] > 0 or (args.strict and counts["AMBER"] > 0)
    report = {
        "schema_version": "1", "platform": PLATFORM, "label": LABEL,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "checks": results, "counts": counts, "verdict": verdict,
        "summary": f"{counts['GREEN']}/{len(results)} GREEN, {counts['AMBER']} AMBER, {counts['RED']} RED",
    }
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"  Platform : {LABEL}")
        print(f"  Verdict  : {verdict}  ({report['summary']})")
        for r in results:
            print(f"    [{r['status']:5}] {r['name']:24}  {r['reason']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
