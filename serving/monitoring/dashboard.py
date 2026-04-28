from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from serving.monitoring.compute_metrics import compute_metrics, load_events


def _with_timeseries(events: list[dict]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame(columns=["timestamp", "backend", "latency_ms", "success"])
    df = pd.DataFrame(events)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    return df


def _windowed_series(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        empty = pd.DataFrame(columns=["timestamp", "value"])
        return empty, empty

    req_series = (
        df.set_index("timestamp")
        .resample("10s")
        .size()
        .rename("requests")
        .reset_index()
    )
    req_series["rps"] = req_series["requests"] / 10.0

    err_df = df.copy()
    err_df["error"] = (~err_df["success"]).astype(int)
    err_series = (
        err_df.set_index("timestamp")
        .resample("10s")["error"]
        .mean()
        .fillna(0.0)
        .rename("error_rate")
        .reset_index()
    )
    return req_series, err_series


def main() -> None:
    st.set_page_config(page_title="Serving Live Monitoring", layout="wide")
    st.title("Serving Live Monitoring")

    source = st.sidebar.selectbox("Log source", ["minio", "local"], index=0)
    backend_filter = st.sidebar.selectbox("Backend", ["all", "fastapi", "ray"], index=0)
    refresh_sec = st.sidebar.slider("Refresh interval (seconds)", min_value=5, max_value=10, value=5)

    backend = None if backend_filter == "all" else backend_filter
    used_source = source
    events = load_events(use_minio=(source == "minio"), backend=backend)
    if source == "minio" and not events:
        events = load_events(use_minio=False, backend=backend)
        if events:
            used_source = "local-fallback"
            st.warning("MinIO returned no events; using local fallback log.")
    metrics = compute_metrics(events)
    df = _with_timeseries(events)
    req_series, err_series = _windowed_series(df)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total requests", int(metrics["total_requests"]))
    c2.metric("Current RPS", f'{metrics["rps"]:.2f}')
    c3.metric("p50 latency (ms)", f'{metrics["p50_latency_ms"]:.2f}')
    c4.metric("p95 latency (ms)", f'{metrics["p95_latency_ms"]:.2f}')
    c5.metric("p99 latency (ms)", f'{metrics["p99_latency_ms"]:.2f}')
    c6.metric("Error rate", f'{metrics["error_rate"] * 100:.2f}%')

    st.subheader("Latency over time")
    if not df.empty:
        st.line_chart(df.set_index("timestamp")["latency_ms"])
    else:
        st.info("No events found.")

    st.subheader("Requests per second over time")
    if not req_series.empty:
        st.line_chart(req_series.set_index("timestamp")["rps"])
    else:
        st.info("No request series yet.")

    st.subheader("Error rate over time")
    if not err_series.empty:
        st.line_chart(err_series.set_index("timestamp")["error_rate"])
    else:
        st.info("No error series yet.")

    st.caption(f"Auto-refreshing every {refresh_sec}s | source={used_source}")
    time.sleep(refresh_sec)
    st.rerun()


if __name__ == "__main__":
    main()
