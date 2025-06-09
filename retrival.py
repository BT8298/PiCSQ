#!/usr/bin/python
"""
Traffic Pi Uploader: 
- Retrieves Jamar TRAX Apollyon GPS data via USB
- Parses total vehicles, per-vehicle timestamps, and attaches a location ID
- Sends compact JSON to a server every 5 minutes

Assumptions:
1) When plugged in, the Apollyon appears under /mnt/usb or /media/pi/APOLLYON (adjust as needed).
2) The Apollyon's exported data file is named like 'TRAX_YYYYMMDD_XXXX.<csv><prn><dmp>' or similar.
3) Location of this Pi's counter is a small integer (LOCATION_ID), known ahead of time (ie. 0 for location A, 1 for location B, etc).
4) Remote server URL (SERVER_URL) accepts POST with JSON of {"location": int, "batch": [{...}, …]}.
"""

import os
import time
import glob
import json
import gzip
import requests

# Global defaults
LOCATION_ID = 3  # explained above, change this for each Raspberry Pi
SERVER_URL = "https://yourserver.example.com/pi_upload" # this will either be our laptop's IP or Acadia's server (if they allow us access)
USB_MOUNT_POINT = "/mnt/usb"  # ASSUMPTION of where the Apollyon auto-mounts when you plug it in, may be different based on below function
POLL_INTERVAL_SEC = 300       # send transmissions every 5 minutes (300 seconds)



def find_device_path():
    """
    Detect the USB mount for the traffic counter. 
    You may need to adjust this if your Pi automounts under /media/pi/APOLLYON or similar.
    Returns the path to the mount (e.g. '/mnt/usb') if found, otherwise None.
    """
    if os.path.isdir(USB_MOUNT_POINT):
        return USB_MOUNT_POINT
    # Try any media folder that contains 'Apollyon' or 'TRAX'
    for candidate in glob.glob("/media/pi/*"):
        if os.path.isdir(candidate) and any(x.lower() in candidate.lower() for x in ("apollyon", "trax")):
            return candidate
    return None

def list_data_files(mount_path):
    """
    Returns a list of data files in the counter's root directory. 
    Typically, these are '*.CSV', '*.PRN', or similar.
    """
    patterns = ["*.csv", "*.CSV", "*.prn", "*.PRN", "*.dmp", "*.DMP"]
    matches = []
    for pat in patterns:
        matches.extend(glob.glob(os.path.join(mount_path, pat)))
    return sorted(matches)

def parse_device_file(filepath):
    """
    Parses a single Apollyon export file, extracting:
    - Per-vehicle records: a list of dicts, each {"timestamp": <ISO8601>} 
    - Total vehicle count: integer
    The exact CSV format can vary. Here's a generic approach:
      - Skip any header lines until you see a known marker (e.g. a "TimeStamp" column)
      - Each subsequent line might be: "YYYY/MM/DD HH:MM:SS,<other fields>,Count=1" 
        or two timestamps per vehicle (front/rear axles). 
    This must be ammended to match the actual file's columns.

    For now, it is assumed that each line is one vehicle record with first column = "YYYY/MM/DD HH:MM:SS".
    WE WILL UPDATE ONCE WE ACTUALLY EXAMINE THE FILE STRUCTURE
    """
    vehicle_records = []
    total_count = 0

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    # Example header detection: find the line that contains "TimeStamp" or something similar (change once we actually examine the file structure)
    header_idx = None
    for i, ln in enumerate(lines):
        if "TimeStamp" in ln or "Date" in ln and "Time" in ln:
            header_idx = i
            break
    if header_idx is None:
        # Location of the timestamp table was not found
        header_idx = -1

    for ln in lines[header_idx+1 :]:
        ln = ln.strip()
        if not ln: # If line is empty, skip it
            continue
        # Example: CSV might be: "2025/06/01 14:23:10,01,SomeOtherField"
        parts = ln.split(",")
        ts_str = parts[0].strip()
        try:
            # Convert to ISO8601 for uniformity
            # Apollyon uses YYYY/MM/DD HH:MM:SS
            t_struct = time.strptime(ts_str, "%Y/%m/%d %H:%M:%S")
            iso_ts = time.strftime("%Y-%m-%dT%H:%M:%S", t_struct)
            vehicle_records.append({"timestamp": iso_ts})
            total_count += 1
        except Exception:
            # If parsing fails, skip line
            continue

    return total_count, vehicle_records

def remove_processed_file(filepath):
    """
    After successful parsing and queuing for upload, remove or move the file
    so we don't re-send it. Here we simply delete it.
    """
    try:
        os.remove(filepath)
    except OSError:
        print(f"IN FILE REMOVAL FUNCTION: Failed to remove file {filepath}")
        pass

def send_batch_to_server(location_id, vehicle_records):
    """
    Packages the data into a compact JSON and sends via HTTP POST.
    We gzip the JSON to shrink bytes-over-the-wire. The server must accept
    `Content-Encoding: gzip`.

    Payload structure:
      {
        "location": 3,
        "batch": [
            {"timestamp": "2025-06-01T14:23:10"},
            {"timestamp": "2025-06-01T14:23:45"},
            ...
        ]
      }
    """
    payload = {
        "location": location_id,
        "batch": vehicle_records
    }
    # Serialize to JSON, then gzip compress (we only have 10 MB per month per device, every bit saved counts!)
    json_bytes = json.dumps(payload, separators=(",",":")).encode("utf-8")
    gz_payload = gzip.compress(json_bytes)

    headers = {
        "Content-Type": "application/json",
        "Content-Encoding": "gzip",
        # Any keys or authorization needed by Acadia's server go here
    }

    try:
        resp = requests.post(SERVER_URL, data=gz_payload, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        # If upload fails, return False so we can retry later
        print(f"[ERROR] Failed to send batch: {e}")
        return False
    return True

def main_loop():
    """
    Main perpetual loop: every 5 minutes,
    1) Look for new data files on the USB mount
    2) Parse each file, collect per-vehicle timestamps
    3) Send one combined batch for ALL new files in this run
    4) Only delete the local files if upload succeeded
    5) Sleep until next interval
    """
    while True:
        mount_path = find_device_path()

        # AFTER TESTING: If the above function call is unable to read the traffic counter, we may have to import an FTDI library
        # This may be a bit complex so we can wait until after testing to see if it needs to be added
        # The header file 'ftd2xx.h' contains some helpful information for this
        if not mount_path:
            print("[INFO] Counter not mounted. Retrying in 60 sec.")
            time.sleep(60)
            continue

        data_files = list_data_files(mount_path)
        if not data_files:
            print(f"[INFO] No new files on {mount_path}. Sleeping...")
            time.sleep(POLL_INTERVAL_SEC) # Loop resumes after 5 minutes to send all of the new files/updated car count, MAYBE REMOVE THIS LINE AFTER TESTING
            continue

        all_vehicle_records = []
        total_vehicles = 0
        for filepath in data_files:
            print(f"[INFO] Parsing file: {filepath}")
            count, records = parse_device_file(filepath)
            total_vehicles += count
            all_vehicle_records.extend(records)

        if all_vehicle_records:
            print(f"[INFO] Parsed {total_vehicles} vehicles from {len(data_files)} files.")
            success = send_batch_to_server(LOCATION_ID, all_vehicle_records)
            if success:
                print("[INFO] Upload succeeded. Removing local files.")
                for fpath in data_files:
                    remove_processed_file(fpath) # Files are only removed if they are successfully transmitted
            else:
                print("[WARN] Upload failed—will retry next cycle.")

        # Wait until next 5-minute interval
        time.sleep(POLL_INTERVAL_SEC)

if __name__ == "__main__":
    main_loop()
