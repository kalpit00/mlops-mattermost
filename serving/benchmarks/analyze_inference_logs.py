from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((p / 100.0) * (len(ordered) - 1)))
    return ordered[idx]


def _load_events(path: Path, runtime: str | None, scenario: str | None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("msg") != "inference_request":
            continue
        if runtime and row.get("runtime") != runtime:
            continue
        if scenario and row.get("scenario") != scenario:
            continue
        events.append(row)
    return events


def _summarize(events: list[dict[str, Any]]) -> dict[str, float]:
    if not events:
        return {
            "count": 0,
            "success_rate_pct": 0.0,
            "error_rate_pct": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
        }

    latencies = [float(e.get("latency_ms", 0.0)) for e in events]
    ok = sum(1 for e in events if 200 <= int(e.get("status_code", 0)) < 300)
    count = len(events)
    error = count - ok
    return {
        "count": float(count),
        "success_rate_pct": (ok / count) * 100.0,
        "error_rate_pct": (error / count) * 100.0,
        "p50_ms": _percentile(latencies, 50),
        "p95_ms": _percentile(latencies, 95),
        "p99_ms": _percentile(latencies, 99),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze inference audit JSONL logs")
    parser.add_argument("--log", type=Path, required=True, help="Path to inference audit JSONL")
    parser.add_argument("--runtime", choices=["fastapi", "ray"], default=None, help="Filter runtime")
    parser.add_argument("--scenario", default=None, help="Filter scenario label")
    args = parser.parse_args()

    events = _load_events(args.log, args.runtime, args.scenario)
    if not events:
        print("No matching events found.")
        return

    by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in events:
        by_scenario[row.get("scenario", "unspecified")].append(row)

    print(f"log={args.log}")
    if args.runtime:
        print(f"runtime={args.runtime}")
    if args.scenario:
        print(f"scenario_filter={args.scenario}")
    print("")

    for scenario, rows in sorted(by_scenario.items()):
        s = _summarize(rows)
        print(f"scenario={scenario}")
        print(f"  count={int(s['count'])}")
        print(f"  success_rate_pct={s['success_rate_pct']:.2f}")
        print(f"  error_rate_pct={s['error_rate_pct']:.2f}")
        print(f"  latency_ms p50={s['p50_ms']:.2f} p95={s['p95_ms']:.2f} p99={s['p99_ms']:.2f}")
        print("")


if __name__ == "__main__":
    main()
