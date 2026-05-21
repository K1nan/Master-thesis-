#!/usr/bin/env python3
"""
Registers 100 fleet devices in ChirpStack via REST API.
For each device it:
  1. Derives a unique DevEUI by incrementing from BASE_DEV_EUI
  2. DELETE /api/devices/{eui}   → removes device if it exists (clean slate)
  3. POST /api/devices           → creates the device fresh
  4. POST /api/devices/{eui}/keys → sets nwkKey
"""

import csv
import sys
import requests

CHIRPSTACK_URL    = "http://10.136.9.46:8090"
API_KEY           = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJjaGlycHN0YWNrIiwiaXNzIjoiY2hpcnBzdGFjayIsInN1YiI6ImRiZTZkNTgyLWU4NWMtNDEyMS1iNDRiLTliMmNhZTAzNjAwNSIsInR5cCI6ImtleSJ9.Nobh2biE140oQBcB8DLJjA7s3qPXLlJwNTp4pFdXTzo"
APPLICATION_ID    = "3bf9f4d9-87ec-4075-bc60-dc741b3a7183"
DEVICE_PROFILE_ID = "feeacc20-4639-47a2-a886-e9f06d885d36"

BASE_DEV_EUI = bytes.fromhex("A04E8A251D8662D4")
NWK_KEY      = "612e488816a88a28888659bce9e414fe"
JOIN_EUI     = "0000000000000000"
NUM_DEVICES  = 100   # 10 boards × 10 devices each
OUTPUT_CSV   = "chirpstack_devices_registered.csv"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json",
}


def dev_eui_from_index(base: bytes, index: int) -> str:
    eui = bytearray(base)
    carry = index
    i = len(eui) - 1
    while carry > 0 and i >= 0:
        carry, eui[i] = divmod(eui[i] + carry, 256)
        i -= 1
    return eui.hex()


def delete_device(dev_eui: str) -> None:
    """Delete device entirely. 404 means it never existed — both are fine."""
    resp = requests.delete(f"{CHIRPSTACK_URL}/api/devices/{dev_eui}", headers=HEADERS)
    if resp.status_code not in (200, 204, 404):
        resp.raise_for_status()


def create_device(dev_eui: str, name: str) -> None:
    payload = {
        "device": {
            "devEui":          dev_eui,
            "name":            name,
            "applicationId":   APPLICATION_ID,
            "deviceProfileId": DEVICE_PROFILE_ID,
            "joinEui":         JOIN_EUI,
            "isDisabled":      False,
        }
    }
    resp = requests.post(f"{CHIRPSTACK_URL}/api/devices", json=payload, headers=HEADERS)
    if resp.status_code not in (200, 204):
        resp.raise_for_status()


def set_device_keys(dev_eui: str) -> None:
    payload = {
        "deviceKeys": {
            "devEui": dev_eui,
            "nwkKey": NWK_KEY,
        }
    }
    resp = requests.post(
        f"{CHIRPSTACK_URL}/api/devices/{dev_eui}/keys",
        json=payload, headers=HEADERS,
    )
    if resp.status_code in (200, 204):
        return
    if resp.ok:
        return
    resp2 = requests.put(
        f"{CHIRPSTACK_URL}/api/devices/{dev_eui}/keys",
        json=payload, headers=HEADERS,
    )
    resp2.raise_for_status()


def main():
    ok = failed = 0

    print(f"Phase 1/2 — deleting {NUM_DEVICES} devices...")
    for i in range(NUM_DEVICES):
        dev_eui = dev_eui_from_index(BASE_DEV_EUI, i)
        try:
            delete_device(dev_eui)
            print(f"  DEL [{i+1:3d}/{NUM_DEVICES}] {dev_eui}")
        except Exception as e:
            print(f"  DEL [{i+1:3d}/{NUM_DEVICES}] {dev_eui} WARNING: {e}")

    print(f"\nPhase 2/2 — creating {NUM_DEVICES} devices...")
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["DevEUI", "Name", "NwkKey", "JoinEUI"])

        for i in range(NUM_DEVICES):
            dev_eui = dev_eui_from_index(BASE_DEV_EUI, i)
            name    = f"fleet-device-{i:03d}"
            try:
                create_device(dev_eui, name)
                set_device_keys(dev_eui)
                writer.writerow([dev_eui, name, NWK_KEY, JOIN_EUI])
                f.flush()
                print(f"  ADD [{i+1:3d}/{NUM_DEVICES}] OK   {dev_eui}  {name}")
                ok += 1
            except Exception as e:
                print(f"  ADD [{i+1:3d}/{NUM_DEVICES}] FAIL {dev_eui} {name}: {e}")
                failed += 1

    print(f"\nDone — created: {ok}, failed: {failed}")
    print(f"Full list saved to {OUTPUT_CSV}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
