"""
Convert ZKTeco attlog.dat to ERPNext Employee Checkin CSV.

Usage:
    python convert_attlog.py attlog.dat output.csv

Or simply:
    python convert_attlog.py
    (defaults to attlog.dat -> employee_checkins.csv in current folder)

What it does:
    - Reads tab-separated attendance records from the device export
    - Maps ZKTeco status codes to ERPNext IN/OUT log types
    - Outputs a CSV ready for ERPNext's Data Import tool

Notes:
    - The 'employee' column needs the Employee ID (like HR-EMP-00001), not
      the Attendance Device ID. After running this script, open the CSV
      and fill in the 'employee' column based on a lookup of your employees.
    - Alternatively, if you set 'Attendance Device ID' on each employee
      in ERPNext, you can use ERPNext's mapping rules during import.
"""

import sys
import csv
import os

# Map ZKTeco status codes to ERPNext log_type
# 0=Check-In, 1=Check-Out, 2=Break-Out, 3=Break-In, 4=OT-In, 5=OT-Out
LOG_TYPE_MAP = {
    "0": "IN",
    "1": "OUT",
    "2": "OUT",
    "3": "IN",
    "4": "IN",
    "5": "OUT",
}

DEVICE_LABEL = "SenseFace4A"


def convert(input_path, output_path):
    if not os.path.exists(input_path):
        print(f"ERROR: Input file not found: {input_path}")
        return False

    rows_written = 0
    rows_skipped = 0

    with open(input_path, "r", encoding="utf-8", errors="replace") as fin, \
         open(output_path, "w", newline="", encoding="utf-8") as fout:

        writer = csv.writer(fout)
        # Header row matching ERPNext Employee Checkin import template
        writer.writerow([
            "attendance_device_id",  # Helper column - lookup against Employee.attendance_device_id
            "employee",              # Fill in after lookup (Employee ID like HR-EMP-00001)
            "time",                  # Timestamp
            "log_type",              # IN or OUT
            "device_id",             # Device identifier
        ])

        for line_num, line in enumerate(fin, 1):
            line = line.strip()
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) < 3:
                # Try space-separated as fallback
                parts = line.split()
                if len(parts) < 3:
                    print(f"  Line {line_num}: skipping malformed: {line!r}")
                    rows_skipped += 1
                    continue

            user_id = parts[0].strip()
            timestamp = parts[1].strip() if len(parts) > 1 else ""
            # Some exports combine date and time as parts[1] and parts[2]
            if len(parts) > 2 and parts[2].strip() and ":" in parts[2]:
                timestamp = f"{parts[1].strip()} {parts[2].strip()}"
                status = parts[3].strip() if len(parts) > 3 else "0"
            else:
                status = parts[2].strip() if len(parts) > 2 else "0"

            log_type = LOG_TYPE_MAP.get(status, "IN")

            writer.writerow([
                user_id,
                "",  # employee - fill in manually or via VLOOKUP in Excel
                timestamp,
                log_type,
                DEVICE_LABEL,
            ])
            rows_written += 1

    print(f"\nDone. Wrote {rows_written} records to {output_path}")
    if rows_skipped:
        print(f"Skipped {rows_skipped} malformed lines")
    print("\nNext steps:")
    print("1. Open the CSV in Excel")
    print("2. Fill the 'employee' column with Employee IDs from ERPNext")
    print("   (use VLOOKUP against your Employee list export)")
    print("3. In ERPNext: Data Import -> New -> Document Type: Employee Checkin")
    print("4. Upload the CSV, click Save, then Start Import")
    return True


if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "attlog.dat"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "employee_checkins.csv"
    convert(input_file, output_file)
