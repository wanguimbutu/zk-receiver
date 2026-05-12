"""
Configuration for ZK ADMS Receiver.
Edit these values for your environment.
"""

# ---------- ERPNext Settings ----------
ERPNEXT_URL = "https://yourcompany.frappe.cloud"     # No trailing slash
ERPNEXT_API_KEY = "your_api_key_here"
ERPNEXT_API_SECRET = "your_api_secret_here"

# ---------- Receiver Network ----------
# Listen on all interfaces so the device on the LAN can reach us
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8081

# ---------- Storage ----------
DB_PATH = "punches.db"
LOG_PATH = "receiver.log"

# ---------- Retry behavior ----------
# How often the background worker rechecks for failed forwards (seconds)
RETRY_INTERVAL_SECONDS = 30

# ---------- Device config response ----------
# This is sent to the device on its initial handshake (GET /iclock/cdata).
# Tells the device what to push and how often.
#
# Common knobs:
#   TransTimes=00:00;14:05    -> times of day to do full sync (HH:MM;HH:MM)
#   TransInterval=1           -> push interval in minutes for new records
#   TransFlag=...             -> bitmask of what data types to push:
#                                AttLog UserInfo Operation FingerprintTemplate FaceTemplate ...
#                                "1111111111" = push everything; "1000000000" = AttLog only
#   Realtime=1                -> 1 = push immediately on punch (recommended)
#   Encrypt=0                 -> 0 = plain text (1 requires matching crypto key)
#   ServerVer=2.4.1           -> some firmwares check this; safe value
#
# These values work for most SenseFace / SpeedFace / ProFace models.
DEVICE_CONFIG_RESPONSE = (
    "GET OPTION FROM: SenseFace4A\n"
    "Stamp=9999\n"
    "OpStamp=9999\n"
    "ErrorDelay=30\n"
    "Delay=10\n"
    "TransTimes=00:00;14:05\n"
    "TransInterval=1\n"
    "TransFlag=1000000000\n"
    "TimeZone=3\n"            # GMT+3 for Kenya (EAT)
    "Realtime=1\n"
    "Encrypt=0\n"
    "ServerVer=2.4.1\n"
)