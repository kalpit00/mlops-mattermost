from __future__ import annotations

import argparse

from .benchmark_http import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Ray Serve endpoint")
    parser.add_argument("--url", default="http://127.0.0.1:8001/")
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--sample", required=False)
    parser.add_argument("--scenario", default=None, help="Scenario label for request audit logs (e.g. low/high)")
    args = parser.parse_args()

    import asyncio
    from pathlib import Path

    sample = Path(args.sample) if args.sample else (Path(__file__).resolve().parent / "sample_requests.jsonl")
    asyncio.run(run(args.url, sample, args.requests, args.concurrency, args.scenario))


if __name__ == "__main__":
    main()
