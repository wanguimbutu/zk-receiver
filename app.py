"""
ZKTeco ADMS Push Receiver for ERPNext
Handles iclock protocol push from SenseFace 4A and similar cloud-mode devices.
Forwards Employee Checkin records to ERPNext via REST API.
"""

import os
import sqlite3
import logging
import threading
import time
from datetime import datetime
from flask import Flask, request, Response
import requests
from config import (
    ERPNEXT_URL,
    ERPNEXT_API_KEY,
    ERPNEXT_API_SECRET,
    LISTEN_HOST,
    LISTEN_PORT,
    DB_PATH,
    LOG_PATH,
    RETRY_INTERVAL_SECONDS,
    DEVICE_CONFIG_RESPONSE,
)

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
log = logging.getLogger("zk-receiver")

# ---------- Database ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS punches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_sn TEXT,
            user_id TEXT,
            timestamp TEXT,
            status TEXT,
            verify_type TEXT,
            raw_line TEXT,
            received_at TEXT,
            forwarded INTEGER DEFAULT 0,
            forward_attempts INTEGER DEFAULT 0,
            last_error TEXT
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_forwarded ON punches(forwarded)")
    conn.commit()
    conn.close()
    log.info(f"Database initialized at {DB_PATH}")


def save_punch(device_sn, user_id, timestamp, status, verify_type, raw_line):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO punches (device_sn, user_id, timestamp, status, verify_type, raw_line, received_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (device_sn, user_id, timestamp, status, verify_type, raw_line, datetime.now().isoformat()))
    punch_id = c.lastrowid
    conn.commit()
    conn.close()
    return punch_id


def mark_forwarded(punch_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE punches SET forwarded=1, last_error=NULL WHERE id=?", (punch_id,))
    conn.commit()
    conn.close()


def mark_failed(punch_id, error_msg):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE punches
        SET forward_attempts = forward_attempts + 1, last_error = ?
        WHERE id = ?
    """, (error_msg, punch_id))
    conn.commit()
    conn.close()


def get_unforwarded():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, user_id, timestamp, status, verify_type
        FROM punches
        WHERE forwarded = 0 AND forward_attempts < 20
        ORDER BY id ASC
        LIMIT 100
    """)
    rows = c.fetchall()
    conn.close()
    return rows


# ---------- ERPNext Forwarding ----------
def forward_to_erpnext(user_id, timestamp_str, status):
    """
    Push an Employee Checkin to ERPNext.
    status mapping: 0=Check-In, 1=Check-Out (ZKTeco default; adjust below if needed)
    """
    # Map ZKTeco status codes to ERPNext log_type
    # Common ZKTeco status: 0=Check-In, 1=Check-Out, 2=Break-Out, 3=Break-In, 4=OT-In, 5=OT-Out
    log_type_map = {
        "0": "IN",
        "1": "OUT",
        "2": "OUT",
        "3": "IN",
        "4": "IN",
        "5": "OUT",
    }
    log_type = log_type_map.get(str(status), "IN")

    # ZKTeco timestamps look like: "2026-05-12 09:42:15"
    # ERPNext expects: "2026-05-12 09:42:15"
    # No transformation usually needed.

    url = f"{ERPNEXT_URL}/api/method/erpnext.hr.doctype.employee_checkin.employee_checkin.add_log_based_on_employee_field"
    headers = {
        "Authorization": f"token {ERPNEXT_API_KEY}:{ERPNEXT_API_SECRET}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = {
        "employee_field_value": str(user_id),
        "timestamp": timestamp_str,
        "device_id": "SenseFace4A",
        "log_type": log_type,
        "employee_fieldname": "attendance_device_id",
    }

    try:
        r = requests.post(url, headers=headers, data=payload, timeout=15)
        if r.status_code == 200:
            return True, None
        else:
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except requests.exceptions.RequestException as e:
        return False, str(e)


def retry_worker():
    """Background thread that retries failed forwards."""
    while True:
        try:
            rows = get_unforwarded()
            if rows:
                log.info(f"Retry worker: {len(rows)} pending punches")
                for punch_id, user_id, timestamp, status, verify_type in rows:
                    ok, err = forward_to_erpnext(user_id, timestamp, status)
                    if ok:
                        mark_forwarded(punch_id)
                        log.info(f"Forwarded punch #{punch_id} user={user_id} ts={timestamp}")
                    else:
                        mark_failed(punch_id, err)
                        log.warning(f"Forward failed for punch #{punch_id}: {err}")
        except Exception as e:
            log.exception(f"Retry worker error: {e}")
        time.sleep(RETRY_INTERVAL_SECONDS)


# ---------- Flask App ----------
app = Flask(__name__)


@app.route("/iclock/cdata", methods=["GET"])
def cdata_get():
    """
    Initial handshake. Device asks for its config.
    We respond with key=value lines telling the device how to behave.
    """
    sn = request.args.get("SN", "unknown")
    options = request.args.get("options", "")
    log.info(f"Handshake from device SN={sn} options={options}")
    return Response(DEVICE_CONFIG_RESPONSE, mimetype="text/plain")


@app.route("/iclock/cdata", methods=["POST"])
def cdata_post():
    """
    Device pushes data here. Could be attendance (ATTLOG) or operation logs (OPERLOG).
    Body format is tab-separated, one record per line.
    """
    sn = request.args.get("SN", "unknown")
    table = request.args.get("table", "")
    stamp = request.args.get("Stamp", "")
    body = request.get_data(as_text=True)

    log.info(f"Push from SN={sn} table={table} stamp={stamp} bytes={len(body)}")

    if table == "ATTLOG":
        count = parse_attlog(sn, body)
        log.info(f"Parsed {count} attendance records from SN={sn}")
        # Reply format: OK: <count>
        return Response(f"OK: {count}", mimetype="text/plain")
    elif table == "OPERLOG":
        log.info(f"Received OPERLOG from SN={sn} (not processed)")
        return Response("OK", mimetype="text/plain")
    else:
        log.info(f"Received unknown table={table} from SN={sn}")
        return Response("OK", mimetype="text/plain")


@app.route("/iclock/getrequest", methods=["GET"])
def getrequest():
    """
    Device polls for commands. We have nothing to send most of the time.
    Return OK to keep the device happy.
    """
    sn = request.args.get("SN", "unknown")
    log.debug(f"getrequest from SN={sn}")
    return Response("OK", mimetype="text/plain")


@app.route("/iclock/devicecmd", methods=["POST"])
def devicecmd():
    """Device reports command execution status."""
    sn = request.args.get("SN", "unknown")
    body = request.get_data(as_text=True)
    log.info(f"devicecmd from SN={sn}: {body[:200]}")
    return Response("OK", mimetype="text/plain")


@app.route("/", methods=["GET"])
def health():
    return "ZK Receiver running\n"


def parse_attlog(sn, body):
    """
    ATTLOG format (tab-separated):
    user_id \t timestamp \t status \t verify_type \t [workcode] \t [reserved1] \t [reserved2]

    Example:
    1001    2026-05-12 09:42:15     0       1       0       0       0
    """
    count = 0
    for line in body.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            log.warning(f"Skipping malformed ATTLOG line: {line!r}")
            continue
        user_id = parts[0].strip()
        timestamp = parts[1].strip()
        status = parts[2].strip()
        verify_type = parts[3].strip()
        save_punch(sn, user_id, timestamp, status, verify_type, line)
        count += 1
    return count


# ---------- Startup ----------
if __name__ == "__main__":
    init_db()
    # Start retry worker thread
    t = threading.Thread(target=retry_worker, daemon=True)
    t.start()
    log.info(f"Starting receiver on {LISTEN_HOST}:{LISTEN_PORT}")
    log.info(f"Forwarding to ERPNext: {ERPNEXT_URL}")
    # Use waitress in production; flask dev server is fine for testing
    try:
        from waitress import serve
        serve(app, host=LISTEN_HOST, port=LISTEN_PORT, threads=4)
    except ImportError:
        log.warning("waitress not installed, using Flask dev server")
        app.run(host=LISTEN_HOST, port=LISTEN_PORT, debug=False)