from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx


def load_requests(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


async def run(url: str, requests_path: Path, total_requests: int, concurrency: int) -> None:
    payloads = load_requests(requests_path)
    latencies_ms: list[float] = []
    ok = 0
    failed = 0

    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(timeout=5.0) as client:
        async def one(i: int) -> None:
            nonlocal ok, failed
            payload = payloads[i % len(payloads)]
            async with sem:
                start = time.perf_counter()
                try:
                    r = await client.post(url, json=payload)
                    elapsed = (time.perf_counter() - start) * 1000
                    latencies_ms.append(elapsed)
                    if r.status_code == 200:
                        ok += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1

        await asyncio.gather(*[one(i) for i in range(total_requests)])

    p50 = statistics.quantiles(latencies_ms, n=100)[49] if latencies_ms else 0.0
    p95 = statistics.quantiles(latencies_ms, n=100)[94] if latencies_ms else 0.0
    p99 = statistics.quantiles(latencies_ms, n=100)[98] if latencies_ms else 0.0

    print(f"url={url}")
    print(f"requests={total_requests} concurrency={concurrency} ok={ok} failed={failed}")
    print(f"latency_ms p50={p50:.2f} p95={p95:.2f} p99={p99:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark FastAPI /score endpoint")
    parser.add_argument("--url", default="http://127.0.0.1:8000/score")
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument(
        "--sample",
        type=Path,
        default=Path(__file__).resolve().parent / "sample_requests.jsonl",
    )
    args = parser.parse_args()

    asyncio.run(run(args.url, args.sample, args.requests, args.concurrency))


if __name__ == "__main__":
    main()
