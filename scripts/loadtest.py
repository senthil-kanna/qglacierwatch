"""Load test for the forecast API (local baseline now; the deployed Azure URL later).

Measures sequential latency (P50/P95/P99) and closed-loop throughput at several concurrency levels.
Results are written as JSON next to the other reports. Not part of CI.

Usage:
    python scripts/loadtest.py --url http://localhost:8002 --label local_uvicorn
    python scripts/loadtest.py --url https://<api-fqdn> --label azure_container_apps --api-key <key>
"""

import argparse
import json
import platform
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np


def timed_get(client: httpx.Client, path: str) -> tuple[float, int]:
    t0 = time.perf_counter()
    r = client.get(path)
    return (time.perf_counter() - t0) * 1000, r.status_code


def sequential(client, path, n) -> dict:
    lat, codes = zip(*(timed_get(client, path) for _ in range(n)), strict=True)
    a = np.array(lat)
    return {"n": n, "p50_ms": float(np.percentile(a, 50)), "p95_ms": float(np.percentile(a, 95)), "p99_ms": float(np.percentile(a, 99)),
            "mean_ms": float(a.mean()), "errors": int(sum(c != 200 for c in codes))}


def concurrent(base, headers, path, workers, seconds) -> dict:
    stop = time.perf_counter() + seconds
    lat, errs = [], 0

    def worker():
        nonlocal errs
        with httpx.Client(base_url=base, headers=headers, timeout=60) as c:
            while time.perf_counter() < stop:
                ms, code = timed_get(c, path)
                lat.append(ms)
                errs += code != 200

    t0 = time.perf_counter()
    with ThreadPoolExecutor(workers) as ex:
        for _ in range(workers):
            ex.submit(worker)
    dur = time.perf_counter() - t0
    a = np.array(lat)
    return {"workers": workers, "seconds": round(dur, 1), "requests": len(a), "throughput_rps": len(a) / dur,
            "p50_ms": float(np.percentile(a, 50)), "p95_ms": float(np.percentile(a, 95)), "errors": errs}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--api-key", default="")
    p.add_argument("--seconds", type=int, default=20)
    args = p.parse_args()
    headers = {"X-API-Key": args.api_key} if args.api_key else {}
    out = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"), "label": args.label, "url": args.url,
           "client": platform.platform(), "python": platform.python_version()}
    with httpx.Client(base_url=args.url, headers=headers, timeout=60) as c:
        for _ in range(5):
            timed_get(c, "/v1/forecast")  # warm-up (also wakes a scaled-to-zero app)
        out["sequential_health"] = sequential(c, "/health", 200)
        out["sequential_forecast"] = sequential(c, "/v1/forecast", 200)
    out["concurrent_forecast"] = [concurrent(args.url, headers, "/v1/forecast", w, args.seconds) for w in (1, 4, 16, 32)]
    path = Path(__file__).resolve().parents[1] / "reports" / "real" / f"loadtest_{args.label}.json"
    path.write_text(json.dumps(out, indent=2))
    s = out["sequential_forecast"]
    print(f"forecast sequential: P50 {s['p50_ms']:.1f} ms, P95 {s['p95_ms']:.1f} ms, errors {s['errors']}")
    for c in out["concurrent_forecast"]:
        print(f"  {c['workers']:>2} workers: {c['throughput_rps']:.1f} req/s, P50 {c['p50_ms']:.1f} ms, P95 {c['p95_ms']:.1f} ms, errors {c['errors']}")
    print(f"health sequential: P50 {out['sequential_health']['p50_ms']:.1f} ms; median of means {statistics.median([out['sequential_health']['mean_ms']]):.1f}")


if __name__ == "__main__":
    main()
