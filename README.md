# Acadia Traffic Monitoring Proof‑of‑Concept

This repository contains two main Python scripts for evaluating and demonstrating cellular-based traffic data collection in Acadia National Park:

## Project Overview

Acadia National Park currently uses 15 Jamar TRAX Apollyon GPS tube counters to record vehicle passages, but data retrieval requires manually visiting each sensor and downloading via USB drive. This proof‑of‑concept project uses Raspberry Pi Zero 2 WH devices equipped with Telit Cinterion modems (via a Sixfab Cellular RF expansion board) to:

1. **Survey cellular signal strength** at potential sensor locations before deployment.
2. **Retrieve and transmit traffic data** from each tube counter to a central server or personal computer every five minutes.

By parsing and compressing only the essential information (timestamps and total counts), we ensure monthly data usage stays well under the 10 MB/device limit of the chosen Verizon IoT plan.

## Repository Contents

* `csq.py`

  * **Purpose:** One‑shot signal‑strength diagnostic script.
  * **Key features:**

    * Auto-detects the Telit ME910G1 modem on `/dev/ttyUSB*`.
    * Sends AT commands (`AT+CSQ`, `AT#WS46?`, etc.) to measure RSSI, network mode (NB‑IoT vs. CAT‑M1), GPS power, and operator list.
    * Parses the `+CSQ` response into an RSSI code and approximate dBm value.
    * Prints a human‑readable summary.
  * **Usage:**

    * There is currently no entry point/main function
    * To test, open the python terminal and run something similar to the below example:
        ```bash
        >>> from csq import TelitME910G1
        >>> m = TelitME910G1()
        >>> m.sim_test()
        >>> m.diagnostic_test()
        ```


* `retrival.py`

  * **Purpose:** Main data‐retrieval and upload loop.
  * **Key features:**

    1. **Mount detection:** Finds the Apollyon’s USB‑mass‑storage mount point (e.g., `/mnt/usb`).
    2. **File discovery:** Scans for new data files (`*.csv`, `*.prn`, etc.).
    3. **Parsing:** Extracts per‑vehicle timestamps and counts from each file, converting to ISO 8601.
    4. **Batching & compression:** Bundles all records into a JSON payload, compresses with gzip to minimize bandwidth.
    5. **Upload:** Sends the batch via HTTP POST to a configurable `SERVER_URL`.
    6. **Cleanup:** Deletes processed files only upon successful upload.
  * **Configuration:** Edit constants at the top of `trafficipi.py` for:

    * `LOCATION_ID` (integer ID for this sensor)
    * `SERVER_URL` (remote endpoint for data ingestion)
    * `USB_MOUNT_POINT` and `POLL_INTERVAL_SEC`
  * **Usage:**

    ```bash
    python3 trafficipi.py
    ```
  * **Recommended:** Run as a `systemd` service to restart on failure and launch at boot.

## Getting Started

1. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```
   `OR`
   
   ```bash
   sudo apt update
   sudo apt install python3-gpiozero python3-pyserial python3-smbus3 python3-requests
   ```
2. **Configure scripts:**

   * Adjust mount points and server URLs in each file.
3. **Test locally:**

   * Plug in a Telit modem and run `csq.py` to verify AT-command responses.
4. **Deploy to Pi:**

   * Copy both scripts to each Raspberry Pi Zero 2 WH.
   * Enable and start the `trafficipi.service` systemd unit (if desired).

## Notes

* The mass‑storage CSV export from the Jamar Apollyon GPS should work natively on Linux; no Windows emulation is required in most cases.
* If the counter only supports FTDI D2XX for direct cable downloads, see the `ftd2xx.h` header for Linux support and plan to install `libftd2xx` or `libftdi`.

---

*For more details on the project, see team members Aaron Abramson, Benjamin Falck-Ytter, Oliver Forbes, and Benjamin Taksa. This project is part of WPI's Interactive Qualifying Project (IQP) program, in collaboration with Acadia National Park.*