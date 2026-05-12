"""
Simulator: pretends to be a SenseFace 4A pushing data to the receiver.
Use this to test the receiver and the ERPNext integration without needing
to walk to the device and punch every time.

Usage:
    python test_simulator.py
"""

import requests
from datetime import datetime

RECEIVER_URL = "http://127.0.0.1:8081"
FAKE_SN = "TEST1234567890"


def test_handshake():
    print("Testing handshake (GET /iclock/cdata)...")
    r = requests.get(f"{RECEIVER_URL}/iclock/cdata", params={"SN": FAKE_SN, "options": "all"})
    print(f"  Status: {r.status_code}")
    print(f"  Body:\n{r.text}")
    print()


def test_attlog_push(user_id="1001", status="0"):
    print(f"Testing ATTLOG push (POST /iclock/cdata) user={user_id} status={status}...")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Tab-separated: user_id, timestamp, status, verify_type, workcode, r1, r2
    body = f"{user_id}\t{now}\t{status}\t1\t0\t0\t0"
    r = requests.post(
        f"{RECEIVER_URL}/iclock/cdata",
        params={"SN": FAKE_SN, "table": "ATTLOG", "Stamp": "9999"},
        data=body,
    )
    print(f"  Status: {r.status_code}")
    print(f"  Body: {r.text}")
    print(f"  Sent: {body!r}")
    print()


def test_getrequest():
    print("Testing getrequest (GET /iclock/getrequest)...")
    r = requests.get(f"{RECEIVER_URL}/iclock/getrequest", params={"SN": FAKE_SN})
    print(f"  Status: {r.status_code}")
    print(f"  Body: {r.text}")
    print()


def test_health():
    print("Testing health endpoint...")
    r = requests.get(f"{RECEIVER_URL}/")
    print(f"  Status: {r.status_code}")
    print(f"  Body: {r.text.strip()}")
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("ZK Receiver Simulator")
    print("=" * 60)
    print()
    try:
        test_health()
        test_handshake()
        test_attlog_push(user_id="1001", status="0")  # check-in
        test_attlog_push(user_id="1001", status="1")  # check-out
        test_getrequest()
        print("All simulator tests sent. Check receiver.log and punches.db.")
    except requests.exceptions.ConnectionError:
        print("ERROR: Could not connect to receiver. Is it running on port 8081?")
