#!/usr/bin/env python3
"""
ChirpStack gateway monitor — SSH system metrics + REST API RF metrics.

Captures every INTERVAL seconds:

  SSH (host system):
    cpu_pct            overall CPU utilisation %
    cpu_user / cpu_sys / cpu_iowait
    mem_total_mb       total RAM (MB)
    mem_used_mb        used RAM (MB)
    mem_free_mb        free RAM (MB)
    mem_used_pct       RAM utilisation %
    load_1 / load_5 / load_15   system load averages
    net_rx_bytes       cumulative bytes received on main NIC
    net_tx_bytes       cumulative bytes transmitted on main NIC
    net_rx_delta       bytes received since last sample
    net_tx_delta       bytes transmitted since last sample
    cs_cpu_pct         chirpstack process CPU %
    cs_mem_mb          chirpstack process RSS (MB)
    pf_cpu_pct         packet-forwarder process CPU %
    pf_mem_mb          packet-forwarder process RSS (MB)

  ChirpStack REST API (gateway RF layer):
    rx_total / tx_total / rx_delta / tx_delta
    rx_crc_ok / rx_crc_error / rx_crc_none / crc_error_rate_pct
    rx_dr0 … rx_dr5   per-data-rate RX counts

Usage:
    python3 gateway_monitor.py                   # uses admin/admin by default
    python3 gateway_monitor.py --ssh-user admin --ssh-pass admin
    python3 gateway_monitor.py --ssh-key ~/.ssh/id_rsa
    python3 gateway_monitor.py --no-ssh          # API only (fallback)
"""

import argparse
import csv
import signal
import sys
import time
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    sys.exit("Install requests:  pip install requests")

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False

# ── CONFIG ────────────────────────────────────────────────────────────────────
CHIRPSTACK_HOST = "10.136.9.46"
CHIRPSTACK_PORT = 8090
SSH_PORT        = 22
API_KEY         = (
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9"
    ".eyJhdWQiOiJjaGlycHN0YWNrIiwiaXNzIjoiY2hpcnBzdGFjayIsInN1YiI6ImRiZTZkNTgyLWU4NWMtNDEyMS1iNDRiLTliMmNhZTAzNjAwNSIsInR5cCI6ImtleSJ9"
    ".Nobh2biE140oQBcB8DLJjA7s3qPXLlJwNTp4pFdXTzo"
)
INTERVAL_S  = 0.1
DURATION_S  = 3000
OUTPUT_FILE = "gateway_metrics.csv"
# ─────────────────────────────────────────────────────────────────────────────

FIELDNAMES = [
    # timing
    "elapsed_s", "timestamp", "gateway_id",
    # SSH — CPU
    "cpu_pct", "cpu_user", "cpu_sys", "cpu_iowait",
    # SSH — memory
    "mem_total_mb", "mem_used_mb", "mem_free_mb", "mem_used_pct",
    # SSH — load
    "load_1", "load_5", "load_15",
    # SSH — network
    "net_rx_bytes", "net_tx_bytes", "net_rx_delta", "net_tx_delta",
    # SSH — processes
    "cs_cpu_pct", "cs_mem_mb", "pf_cpu_pct", "pf_mem_mb",
    # API — RF totals
    "rx_total", "tx_total", "rx_delta", "tx_delta",
    # API — CRC
    "rx_crc_ok", "rx_crc_error", "rx_crc_none", "crc_error_rate_pct",
    # API — per DR
    "rx_dr0", "rx_dr1", "rx_dr2", "rx_dr3", "rx_dr4", "rx_dr5",
]

records:   list[dict] = []
stop_flag: bool       = False


# ── SSH helpers ───────────────────────────────────────────────────────────────

def ssh_connect(host: str, port: int, user: str,
                password: str | None, key_path: str | None) -> "paramiko.SSHClient":
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs = dict(
        hostname=host, port=port, username=user, timeout=10,
        look_for_keys=False, allow_agent=False,
    )
    if key_path:
        kwargs["key_filename"] = key_path
        kwargs.pop("look_for_keys", None)
    else:
        kwargs["password"] = password
    # Try password auth first; fall back to keyboard-interactive
    try:
        client.connect(**kwargs)
        return client
    except paramiko.AuthenticationException:
        pass
    # keyboard-interactive (some embedded Linux gateways require this)
    transport = paramiko.Transport((host, port))
    transport.connect()
    transport.auth_interactive_dumb(user, lambda t, i, p: [password or ""] * len(p))
    client._transport = transport
    return client


def ssh_run(client: "paramiko.SSHClient", cmd: str) -> str:
    _, stdout, _ = client.exec_command(cmd, timeout=8)
    return stdout.read().decode(errors="replace")


def collect_ssh_metrics(client: "paramiko.SSHClient",
                        prev_cpu: dict | None,
                        prev_net: dict | None,
                        net_iface: str) -> tuple[dict, dict, dict]:
    """
    Returns (metrics_dict, raw_cpu_counters, raw_net_counters).
    Pass the raw counters back in next call to compute deltas.
    """
    out = {}

    # ── /proc/stat → CPU ──────────────────────────────────────────────────────
    try:
        stat = ssh_run(client, "cat /proc/stat")
        for line in stat.splitlines():
            if line.startswith("cpu "):
                fields = line.split()
                user   = int(fields[1])
                nice   = int(fields[2])
                system = int(fields[3])
                idle   = int(fields[4])
                iowait = int(fields[5]) if len(fields) > 5 else 0
                total  = user + nice + system + idle + iowait
                raw_cpu = {"user": user, "system": system, "idle": idle,
                           "iowait": iowait, "total": total}
                if prev_cpu:
                    dt = raw_cpu["total"] - prev_cpu["total"]
                    if dt > 0:
                        out["cpu_user"]   = round((raw_cpu["user"]   - prev_cpu["user"])   / dt * 100, 1)
                        out["cpu_sys"]    = round((raw_cpu["system"] - prev_cpu["system"]) / dt * 100, 1)
                        out["cpu_iowait"] = round((raw_cpu["iowait"] - prev_cpu["iowait"]) / dt * 100, 1)
                        idle_pct = round((raw_cpu["idle"] - prev_cpu["idle"]) / dt * 100, 1)
                        out["cpu_pct"]    = round(100 - idle_pct, 1)
                break
    except Exception as e:
        raw_cpu = prev_cpu or {}
        print(f"  [WARN] CPU read failed: {e}")

    # ── /proc/meminfo → memory ────────────────────────────────────────────────
    try:
        meminfo = ssh_run(client, "cat /proc/meminfo")
        mem = {}
        for line in meminfo.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                mem[k.strip()] = int(v.strip().split()[0])  # kB
        total_mb = mem.get("MemTotal", 0) // 1024
        free_mb  = mem.get("MemAvailable", mem.get("MemFree", 0)) // 1024
        used_mb  = total_mb - free_mb
        out["mem_total_mb"] = total_mb
        out["mem_used_mb"]  = used_mb
        out["mem_free_mb"]  = free_mb
        out["mem_used_pct"] = round(used_mb / total_mb * 100, 1) if total_mb else 0
    except Exception as e:
        print(f"  [WARN] memory read failed: {e}")

    # ── /proc/loadavg ─────────────────────────────────────────────────────────
    try:
        loadavg = ssh_run(client, "cat /proc/loadavg").split()
        out["load_1"]  = float(loadavg[0])
        out["load_5"]  = float(loadavg[1])
        out["load_15"] = float(loadavg[2])
    except Exception as e:
        print(f"  [WARN] loadavg read failed: {e}")

    # ── /proc/net/dev → network ───────────────────────────────────────────────
    raw_net = prev_net or {}
    try:
        netdev = ssh_run(client, "cat /proc/net/dev")
        for line in netdev.splitlines():
            if net_iface in line:
                parts = line.split()
                rx_bytes = int(parts[1])
                tx_bytes = int(parts[9])
                raw_net = {"rx": rx_bytes, "tx": tx_bytes}
                out["net_rx_bytes"] = rx_bytes
                out["net_tx_bytes"] = tx_bytes
                if prev_net:
                    out["net_rx_delta"] = rx_bytes - prev_net["rx"]
                    out["net_tx_delta"] = tx_bytes - prev_net["tx"]
                break
    except Exception as e:
        print(f"  [WARN] net/dev read failed: {e}")

    # ── ps → per-process stats ────────────────────────────────────────────────
    try:
        ps = ssh_run(client,
            "ps aux | grep -E 'chirpstack|packet[-_]forwarder|lora_pkt' | grep -v grep")
        cs_cpu = cs_mem = pf_cpu = pf_mem = 0.0
        for line in ps.splitlines():
            parts = line.split()
            if len(parts) < 6:
                continue
            cpu = float(parts[2])
            mem_mb = float(parts[5]) / 1024  # VSZ in kB → MB (use RSS at col 5)
            cmd = " ".join(parts[10:]).lower()
            if "chirpstack" in cmd and "forwarder" not in cmd:
                cs_cpu += cpu
                cs_mem += mem_mb
            elif any(x in cmd for x in ["forwarder", "lora_pkt"]):
                pf_cpu += cpu
                pf_mem += mem_mb
        out["cs_cpu_pct"] = round(cs_cpu, 1)
        out["cs_mem_mb"]  = round(cs_mem, 1)
        out["pf_cpu_pct"] = round(pf_cpu, 1)
        out["pf_mem_mb"]  = round(pf_mem, 1)
    except Exception as e:
        print(f"  [WARN] ps read failed: {e}")

    return out, raw_cpu, raw_net


def detect_main_iface(client: "paramiko.SSHClient") -> str:
    """Return the name of the default route network interface."""
    try:
        out = ssh_run(client, "ip route show default")
        for tok in out.split():
            if tok == "dev":
                return out.split()[out.split().index("dev") + 1]
    except Exception:
        pass
    return "eth0"


# ── ChirpStack API helpers ────────────────────────────────────────────────────

def api_get(session: requests.Session, base_url: str,
            path: str, params: dict = None) -> dict:
    r = session.get(f"{base_url}{path}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def discover_gateways(session: requests.Session, base_url: str) -> list[dict]:
    data = api_get(session, base_url, "/api/gateways", {"limit": 100})
    gateways = data.get("result", [])
    if not gateways:
        sys.exit("[ERROR] No gateways found in ChirpStack.")
    return gateways


def _sum_last(metric: dict) -> int:
    total = 0
    for ds in metric.get("datasets", []):
        vals = ds.get("data", [])
        if vals:
            total += int(vals[-1] or 0)
    return total


def _label_last(metric: dict, label: str) -> int:
    for ds in metric.get("datasets", []):
        if ds.get("label", "").upper() == label.upper():
            vals = ds.get("data", [])
            return int(vals[-1] or 0) if vals else 0
    return 0


def fetch_api_metrics(session: requests.Session, base_url: str,
                      gateway_id: str, start: datetime, end: datetime) -> dict:
    params = {
        "start":       start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end":         end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "aggregation": "HOUR",
    }
    try:
        data = api_get(session, base_url,
                       f"/api/gateways/{gateway_id}/metrics", params)
    except Exception as e:
        print(f"  [WARN] API metrics failed: {e}")
        return {}

    rx  = _sum_last(data.get("rxPackets", {}))
    tx  = _sum_last(data.get("txPackets", {}))
    crc = data.get("gwRxPacketsPerStatus", {})
    ok  = _label_last(crc, "CRC_OK")
    err = _label_last(crc, "CRC_ERROR")
    non = _label_last(crc, "NO_CRC")
    tot = ok + err + non
    dr  = data.get("gwRxPacketsPerDr", {})

    return {
        "rx_packets":         rx,
        "tx_packets":         tx,
        "rx_crc_ok":          ok,
        "rx_crc_error":       err,
        "rx_crc_none":        non,
        "crc_error_rate_pct": round(err / tot * 100, 2) if tot else 0.0,
        **{f"rx_dr{i}": _label_last(dr, f"DR{i}") for i in range(6)},
    }


# ── CSV / summary ─────────────────────────────────────────────────────────────

def save_csv(output: str):
    if not records:
        print("[WARN] No data collected.")
        return
    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)

    cpu_vals = [r["cpu_pct"] for r in records if r.get("cpu_pct") is not None]
    mem_vals = [r["mem_used_pct"] for r in records if r.get("mem_used_pct") is not None]
    rx_vals  = [r["rx_delta"] for r in records if r.get("rx_delta") is not None]

    print(f"\n{'='*60}")
    print(f"  Samples   : {len(records)}")
    if cpu_vals:
        print(f"  CPU %     : min={min(cpu_vals):.1f}  "
              f"avg={sum(cpu_vals)/len(cpu_vals):.1f}  max={max(cpu_vals):.1f}")
    if mem_vals:
        print(f"  RAM %     : min={min(mem_vals):.1f}  "
              f"avg={sum(mem_vals)/len(mem_vals):.1f}  max={max(mem_vals):.1f}")
    if rx_vals:
        print(f"  RX Δ/smpl : min={min(rx_vals)}  "
              f"avg={sum(rx_vals)/len(rx_vals):.1f}  max={max(rx_vals)}")
    print(f"  Saved     : {output}")
    print(f"{'='*60}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    global stop_flag

    ap = argparse.ArgumentParser()
    ap.add_argument("--host",     default=CHIRPSTACK_HOST)
    ap.add_argument("--port",     type=int, default=CHIRPSTACK_PORT)
    ap.add_argument("--apikey",   default=API_KEY)
    ap.add_argument("--ssh-user", default="ghlab", help="SSH username")
    ap.add_argument("--ssh-pass", default="ghlab", help="SSH password")
    ap.add_argument("--ssh-key",  default=None,  help="Path to SSH private key")
    ap.add_argument("--ssh-port", type=int, default=SSH_PORT)
    ap.add_argument("--no-ssh",   action="store_true", help="Disable SSH, API only")
    ap.add_argument("--interval", type=float, default=INTERVAL_S)
    ap.add_argument("--duration", type=int,   default=DURATION_S)
    ap.add_argument("--output",   default=OUTPUT_FILE)
    args = ap.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    # ── SSH setup ────────────────────────────────────────────────────────────
    ssh_client = None
    net_iface  = "eth0"
    use_ssh    = not args.no_ssh and (args.ssh_user is not None)

    if use_ssh:
        if not HAS_PARAMIKO:
            print("[WARN] paramiko not installed — falling back to API-only mode.")
            use_ssh = False
        else:
            print(f"[INFO] Connecting SSH to {args.host}:{args.ssh_port} as {args.ssh_user} …")
            try:
                ssh_client = ssh_connect(args.host, args.ssh_port,
                                         args.ssh_user, args.ssh_pass, args.ssh_key)
                net_iface  = detect_main_iface(ssh_client)
                print(f"[INFO] SSH connected. Main NIC: {net_iface}")
            except Exception as e:
                print(f"[WARN] SSH failed: {e} — falling back to API-only mode.")
                use_ssh = False

    if not use_ssh:
        print("[INFO] SSH disabled — collecting API metrics only.")

    # ── ChirpStack API setup ─────────────────────────────────────────────────
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {args.apikey}"

    print(f"[INFO] ChirpStack API at {base_url} …")
    try:
        gateways = discover_gateways(session, base_url)
    except Exception as e:
        sys.exit(f"[ERROR] Cannot reach ChirpStack API: {e}")

    print(f"[INFO] Found {len(gateways)} gateway(s):")
    for gw in gateways:
        print(f"  • {gw.get('gatewayId','?')}  ({gw.get('name','')})")

    gw         = gateways[0]
    gateway_id = gw.get("gatewayId", gw.get("id", ""))
    print(f"[INFO] Monitoring: {gateway_id}")
    print(f"[INFO] Interval={args.interval}s  Duration={args.duration}s  "
          f"Output={args.output}\n")

    def _shutdown(sig, frame):
        global stop_flag
        print("\n[INFO] Interrupted — saving…")
        stop_flag = True

    signal.signal(signal.SIGINT, _shutdown)

    prev_rx_api: int | None = None
    prev_tx_api: int | None = None
    prev_cpu:  dict | None  = None
    prev_net:  dict | None  = None
    start_wall = time.monotonic()

    while not stop_flag:
        elapsed = time.monotonic() - start_wall
        if elapsed > args.duration:
            break

        now          = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=2)
        rec          = {f: None for f in FIELDNAMES}
        rec["elapsed_s"] = round(elapsed, 1)
        rec["timestamp"] = now.strftime("%Y-%m-%dT%H:%M:%S")
        rec["gateway_id"] = gateway_id

        # ── SSH metrics ───────────────────────────────────────────────────────
        if ssh_client:
            try:
                ssh_m, prev_cpu, prev_net = collect_ssh_metrics(
                    ssh_client, prev_cpu, prev_net, net_iface)
                rec.update(ssh_m)
            except Exception as e:
                print(f"  [WARN] SSH collection error: {e}")

        # ── API metrics ───────────────────────────────────────────────────────
        api_m = fetch_api_metrics(session, base_url, gateway_id,
                                  window_start, now)
        rx = api_m.get("rx_packets")
        tx = api_m.get("tx_packets")
        rec["rx_total"]  = rx
        rec["tx_total"]  = tx
        rec["rx_delta"]  = (rx - prev_rx_api) if (rx is not None and prev_rx_api is not None) else None
        rec["tx_delta"]  = (tx - prev_tx_api) if (tx is not None and prev_tx_api is not None) else None
        rec["rx_crc_ok"]          = api_m.get("rx_crc_ok")
        rec["rx_crc_error"]       = api_m.get("rx_crc_error")
        rec["rx_crc_none"]        = api_m.get("rx_crc_none")
        rec["crc_error_rate_pct"] = api_m.get("crc_error_rate_pct")
        for i in range(6):
            rec[f"rx_dr{i}"] = api_m.get(f"rx_dr{i}")

        if rx is not None:
            prev_rx_api = rx
        if tx is not None:
            prev_tx_api = tx

        records.append(rec)

        # ── console line ──────────────────────────────────────────────────────
        cpu_s = f"  CPU={rec['cpu_pct']}%" if rec.get("cpu_pct") is not None else ""
        mem_s = f"  RAM={rec['mem_used_pct']}%" if rec.get("mem_used_pct") is not None else ""
        rx_s  = f"  rx={rx}" + (f"(+{rec['rx_delta']})" if rec["rx_delta"] is not None else "")
        crc_s = f"  CRC_ERR={rec['rx_crc_error']}" if rec.get("rx_crc_error") else ""
        print(f"  t={elapsed:6.1f}s{cpu_s}{mem_s}{rx_s}{crc_s}")

        time.sleep(args.interval)

    if ssh_client:
        ssh_client.close()
    save_csv(args.output)


if __name__ == "__main__":
    main()
