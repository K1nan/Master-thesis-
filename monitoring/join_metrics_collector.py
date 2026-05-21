#!/usr/bin/env python3
"""
Join metrics collector — polls ChirpStack REST API and records every
successful join by detecting when a device's lastSeenAt timestamp changes.

Outputs:
  join_events.csv   — one row per successful join (elapsed_ms, dev_eui, ...)
  join_summary.csv  — aggregate stats after the run ends

Usage:
    python3 join_metrics_collector.py
    python3 join_metrics_collector.py --devices 50 --timeout 600
"""

import argparse
import csv
import signal
import sys
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    sys.exit("Install requests:  pip install requests")

# ── CONFIG ────────────────────────────────────────────────────────────────────
CHIRPSTACK_HOST  = "10.136.9.46"
CHIRPSTACK_PORT  = 8090
APPLICATION_ID   = "3bf9f4d9-87ec-4075-bc60-dc741b3a7183"
API_KEY          = (
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9"
    ".eyJhdWQiOiJjaGlycHN0YWNrIiwiaXNzIjoiY2hpcnBzdGFjayIsInN1YiI6ImRiZTZkNTgyLWU4NWMtNDEyMS1iNDRiLTliMmNhZTAzNjAwNSIsInR5cCI6ImtleSJ9"
    ".Nobh2biE140oQBcB8DLJjA7s3qPXLlJwNTp4pFdXTzo"
)
NUM_DEVICES      = 100   # 10 boards × 10 devices
POLL_INTERVAL_S  = 2       # how often to poll the API
EXPERIMENT_TIMEOUT_S = 600 # stop after this many seconds idle
OUTPUT_EVENTS    = "join_events.csv"
OUTPUT_SUMMARY   = "join_summary.csv"
# ─────────────────────────────────────────────────────────────────────────────

join_events: list[dict] = []
stop_flag = False


def parse_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    ts_str = ts_str.rstrip("Z").split(".")[0]
    return datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)


def fetch_devices(session: requests.Session, base_url: str) -> list[dict]:
    devices = []
    limit = 100
    offset = 0
    while True:
        r = session.get(
            f"{base_url}/api/devices",
            params={"applicationId": APPLICATION_ID, "limit": limit, "offset": offset},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        batch = data.get("result", [])
        devices.extend(batch)
        if len(devices) >= int(data.get("totalCount", 0)):
            break
        offset += limit
    return devices


def save_results(num_devices: int):
    if not join_events:
        print("[WARN] No join events recorded.")
        return

    with open(OUTPUT_EVENTS, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["elapsed_ms", "dev_eui",
                                                "device_name", "last_seen_at"])
        writer.writeheader()
        writer.writerows(join_events)

    latencies = [e["elapsed_ms"] for e in join_events]
    success   = len(join_events)
    summary   = {
        "total_devices":     num_devices,
        "successful_joins":  success,
        "failed_joins":      num_devices - success,
        "success_rate_pct":  round(success / num_devices * 100, 2),
        "min_latency_ms":    min(latencies),
        "max_latency_ms":    max(latencies),
        "avg_latency_ms":    round(sum(latencies) / len(latencies), 1),
        "total_duration_ms": max(latencies),
    }

    with open(OUTPUT_SUMMARY, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=summary.keys())
        writer.writeheader()
        writer.writerow(summary)

    print(f"\n{'='*55}")
    print(f"  Successful joins : {success}/{num_devices} ({summary['success_rate_pct']}%)")
    print(f"  Latency (ms)     : min={summary['min_latency_ms']}  "
          f"avg={summary['avg_latency_ms']}  max={summary['max_latency_ms']}")
    print(f"  Duration         : {summary['total_duration_ms']} ms")
    print(f"{'='*55}")
    print(f"  Saved: {OUTPUT_EVENTS}  |  {OUTPUT_SUMMARY}")


def main():
    global stop_flag

    ap = argparse.ArgumentParser()
    ap.add_argument("--host",    default=CHIRPSTACK_HOST)
    ap.add_argument("--port",    type=int, default=CHIRPSTACK_PORT)
    ap.add_argument("--app-id",  default=APPLICATION_ID)
    ap.add_argument("--devices", type=int, default=NUM_DEVICES)
    ap.add_argument("--timeout", type=int, default=EXPERIMENT_TIMEOUT_S)
    ap.add_argument("--poll",    type=float, default=POLL_INTERVAL_S,
                    help="API poll interval in seconds (default 2)")
    args = ap.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    session  = requests.Session()
    session.headers["Authorization"] = f"Bearer {API_KEY}"

    def _shutdown(sig, frame):
        global stop_flag
        print("\n[INFO] Interrupted — saving results…")
        stop_flag = True

    signal.signal(signal.SIGINT, _shutdown)

    print(f"[INFO] ChirpStack REST API at {base_url}")
    print(f"[INFO] Fetching device list for app {args.app_id} …")

    try:
        devices = fetch_devices(session, base_url)
    except Exception as e:
        sys.exit(f"[ERROR] Cannot fetch devices: {e}")

    print(f"[INFO] Tracking {len(devices)} devices  (expecting {args.devices})")
    print(f"[INFO] Poll interval={args.poll}s  Timeout={args.timeout}s")
    print(f"[INFO] Waiting — start flashing the ESP now…\n")

    # snapshot: devEui -> lastSeenAt before experiment
    baseline: dict[str, datetime | None] = {
        d["devEui"]: parse_ts(d.get("lastSeenAt")) for d in devices
    }
    joined_set: set[str] = set()

    experiment_start = time.monotonic()
    last_join_time   = experiment_start

    while not stop_flag:
        time.sleep(args.poll)

        try:
            current_devices = fetch_devices(session, base_url)
        except Exception as e:
            print(f"[WARN] Poll failed: {e}")
            continue

        now_mono = time.monotonic()
        elapsed_ms = int((now_mono - experiment_start) * 1000)

        for d in current_devices:
            eui = d["devEui"]
            if eui in joined_set:
                continue
            cur_ts  = parse_ts(d.get("lastSeenAt"))
            base_ts = baseline.get(eui)
            if cur_ts is None:
                continue
            # device is newly seen or seen more recently than baseline
            if base_ts is None or cur_ts > base_ts:
                joined_set.add(eui)
                last_join_time = now_mono
                record = {
                    "elapsed_ms":   elapsed_ms,
                    "dev_eui":      eui,
                    "device_name":  d.get("name", ""),
                    "last_seen_at": d.get("lastSeenAt", ""),
                }
                join_events.append(record)
                n = len(join_events)
                print(f"  [{n:3d}/{args.devices}] JOIN  {eui}  +{elapsed_ms} ms  ({d.get('name','')})")

        if len(joined_set) >= args.devices:
            print("[INFO] All devices joined.")
            break

        idle_s = now_mono - last_join_time
        if idle_s > args.timeout:
            print(f"[INFO] No new join for {args.timeout}s — stopping.")
            break

    save_results(args.devices)


if __name__ == "__main__":
    main()
