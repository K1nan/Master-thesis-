#!/usr/bin/env python3
"""
Parse fleet join results from the firmware serial log.

The firmware logs lines like:
    [00:01:23.456] <inf> lorawan: FLEET_CSV,3,a04e8a251d8662d7,1,4821,123456

Usage:
    # Capture serial while device runs:
    python3 parse_serial.py --port /dev/ttyUSB0 --baud 115200 --output firmware_joins.csv

    # Or parse a previously captured log file:
    python3 parse_serial.py --file serial_log.txt --output firmware_joins.csv
"""

import argparse
import csv
import sys

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

HEADER_MARKER = "FLEET_CSV_HDR"
ROW_MARKER    = "FLEET_CSV"
OUTPUT_DEFAULT = "firmware_joins.csv"


def parse_line(line: str) -> dict | None:
    """Extract fields from a FLEET_CSV log line."""
    idx = line.find(ROW_MARKER + ",")
    if idx == -1:
        return None
    csv_part = line[idx + len(ROW_MARKER) + 1:].strip()
    parts = csv_part.split(",")
    if len(parts) < 5:
        return None
    try:
        return {
            "idx":        int(parts[0]),
            "dev_eui":    parts[1],
            "success":    int(parts[2]),
            "latency_ms": int(parts[3]),
            "uptime_ms":  int(parts[4]),
        }
    except ValueError:
        return None


def parse_file(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            rec = parse_line(line)
            if rec:
                rows.append(rec)
    return rows


def parse_serial_port(port: str, baud: int, num_devices: int) -> list[dict]:
    if not SERIAL_AVAILABLE:
        sys.exit("Install pyserial:  pip install pyserial")

    ser = serial.Serial(port, baud, timeout=2)
    rows: list[dict] = []
    print(f"[SERIAL] Listening on {port} @ {baud}…  (waiting for FLEET_CSV lines)")

    while True:
        try:
            raw = ser.readline().decode(errors="replace")
        except serial.SerialException as e:
            print(f"[SERIAL] Error: {e}")
            break

        rec = parse_line(raw)
        if rec:
            rows.append(rec)
            status = "OK  " if rec["success"] else "FAIL"
            print(f"  [{rec['idx']+1:3d}] {status} {rec['dev_eui']}  {rec['latency_ms']} ms")
            if len(rows) >= num_devices:
                print("[INFO] All devices processed — closing serial.")
                break

    ser.close()
    return rows


def save_csv(rows: list[dict], output: str):
    if not rows:
        print("[WARN] No FLEET_CSV rows found.")
        return

    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    success = sum(r["success"] for r in rows)
    total   = len(rows)
    latencies = [r["latency_ms"] for r in rows]
    print(f"\n{'='*50}")
    print(f"  Rows parsed       : {total}")
    print(f"  Successful joins  : {success}/{total} ({success/total*100:.1f}%)")
    print(f"  Latency (ms)      : min={min(latencies)}  "
          f"avg={int(sum(latencies)/len(latencies))}  max={max(latencies)}")
    print(f"  Saved: {output}")
    print(f"{'='*50}")


def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--port", help="Serial port  (e.g. /dev/ttyUSB0)")
    group.add_argument("--file", help="Pre-captured log file")
    ap.add_argument("--baud",    type=int, default=115200)
    ap.add_argument("--devices", type=int, default=100)
    ap.add_argument("--output",  default=OUTPUT_DEFAULT)
    args = ap.parse_args()

    if args.file:
        rows = parse_file(args.file)
    else:
        rows = parse_serial_port(args.port, args.baud, args.devices)

    save_csv(rows, args.output)


if __name__ == "__main__":
    main()
