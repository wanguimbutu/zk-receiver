"""
Convert ZKTeco SenseFace 4A BKtransaction.dat to ERPNext Employee Checkin CSV.

This script handles the BINARY format used by newer ZKTeco devices
(SenseFace 4A and similar) where attendance is stored as fixed-size
binary records, not plain text.

Format reverse-engineered from device serial PYA*, firmware ZAM70-NF43VA:
  - Header: device serial + firmware version + some metadata
  - First record starts at offset 0x53
  - Each record is 28 bytes:
      bytes [0:4]   = timestamp (LE uint32, seconds since 2000-01-01)
      bytes [4:16]  = padding/reserved
      bytes [16:20] = user ID (LE uint32)
      bytes [20:24] = reserved
      byte  [24]    = verify type (15=face, 1=fingerprint, 4=password, etc.)
      byte  [25]    = punch status (0=in, 1=out, 2=break-out, ...)
      bytes [26:28] = reserved

Usage:
    python convert_attlog.py BKtransaction.dat employee_checkins.csv

Or just:
    python convert_attlog.py
    (defaults to BKtransaction.dat -> employee_checkins.csv)
"""

import sys
import csv
import os
from datetime import datetime, timedelta
from collections import Counter

# ZKTeco timestamp epoch
ZK_EPOCH = datetime(2000, 1, 1)

# Record structure
FIRST_RECORD_OFFSET = 0x53
RECORD_SIZE = 28

# Map punch status -> ERPNext log_type
LOG_TYPE_MAP = {
    0: "IN",
    1: "OUT",
    2: "OUT",
    3: "IN",
    4: "IN",
    5: "OUT",
}

VERIFY_NAMES = {
    1: "PIN/Password",
    4: "Card",
    15: "Face",
    200: "Other",
}

DEVICE_LABEL = "SenseFace4A"


def decode_records(data):
    records = []
    offset = FIRST_RECORD_OFFSET
    while offset + RECORD_SIZE <= len(data):
        rec = data[offset:offset + RECORD_SIZE]
        ts = int.from_bytes(rec[0:4], 'little')
        if ts < 100000000 or ts > 2000000000:
            offset += RECORD_SIZE
            continue
        dt = ZK_EPOCH + timedelta(seconds=ts)
        user_id = int.from_bytes(rec[16:20], 'little')
        verify_type = rec[24]
        status = rec[25]
        records.append({
            'time': dt,
            'user_id': user_id,
            'status': status,
            'verify_type': verify_type,
        })
        offset += RECORD_SIZE
    return records


def write_csv(records, output_path):
    with open(output_path, 'w', newline='', encoding='utf-8') as fout:
        writer = csv.writer(fout)
        writer.writerow([
            "attendance_device_id",
            "employee",
            "time",
            "log_type",
            "device_id",
        ])
        for r in records:
            writer.writerow([
                r['user_id'],
                "",
                r['time'].strftime("%Y-%m-%d %H:%M:%S"),
                LOG_TYPE_MAP.get(r['status'], "IN"),
                DEVICE_LABEL,
            ])


def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else "BKtransaction.dat"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "employee_checkins.csv"

    if not os.path.exists(input_file):
        print(f"ERROR: Input file not found: {input_file}")
        print("Usage: python convert_attlog.py <input.dat> <output.csv>")
        sys.exit(1)

    with open(input_file, 'rb') as f:
        data = f.read()

    print(f"Read {len(data)} bytes from {input_file}")

    try:
        if len(data) > 40:
            serial = data[1:14].decode('ascii', errors='replace').strip()
            firmware = data[15:37].decode('ascii', errors='replace').strip()
            print(f"  Device serial:    {serial}")
            print(f"  Firmware version: {firmware}")
    except Exception:
        pass

    records = decode_records(data)
    print(f"\nDecoded {len(records)} attendance records")

    if not records:
        print("No records found. Check that this is the correct file.")
        sys.exit(1)

    users = set(r['user_id'] for r in records)
    print(f"  Unique users:  {len(users)}")
    print(f"  Date range:    {records[0]['time']} to {records[-1]['time']}")

    now = datetime.now()
    future_records = sum(1 for r in records if r['time'] > now)
    if future_records:
        print(f"\n!!! WARNING: {future_records} records have FUTURE dates !!!")
        print("    Your device clock is set incorrectly.")
        print("    Fix at: Menu -> System -> Date/Time before next export.")

    verify_counts = Counter(r['verify_type'] for r in records)
    print(f"\n  Verification methods:")
    for v, count in verify_counts.most_common():
        name = VERIFY_NAMES.get(v, f"Unknown ({v})")
        print(f"    {name}: {count}")

    write_csv(records, output_file)
    print(f"\nWrote CSV to {output_file}")

    print("\nNext steps:")
    print("  1. Open the CSV in Excel to inspect")
    print("  2. Fill in the 'employee' column with ERPNext Employee IDs")
    print("     (VLOOKUP attendance_device_id against your Employee list)")
    print("  3. ERPNext: Data Import -> New -> Document Type: Employee Checkin")
    print("  4. Upload, Save, then Start Import")


if __name__ == "__main__":
    main()
