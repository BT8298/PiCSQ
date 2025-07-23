# Overview
A set of python modules and scripts used in measuring LTE-M and NB-IoT network connection parameters.
Written as part of the Interactive Qualifying Project at Worcester Polytechnic Institute.
This software is designed for and tested on a Raspberry Pi Zero 2 board, with
- Sixfab 3G/4G & LTE Base HAT
- Telit ME910G1 (mPCIe)
- Waveshare Sense HAT (B)
as peripherals.
# Installation
Install the python dependencies via `pip install -r requirements.txt`.
Then run the `install.sh` script as root.
This will add the modules to the system-wide python modules directory, move the scripts to /usr/bin, install the systemd service, and enable it to start on next boot.
# Usage
## `smartpark_data_logger.py`
The file should be installed to /usr/bin/smartpark_data_logger, if using the installation script.
Open with a text editor to input the domain name of the server and desired endpoint (among other values).
This script also has a systemd service unit; start it via
`systemctl start smartpark.service`.
## `get_rx_stats.py`
Run directly with python on the commandline.
Provide the `-h` option to get help.
This script will record location and connection information to a csv file.
The script assumes the modem is already registered on a network.
<--
# Repository Contents

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
!-->
