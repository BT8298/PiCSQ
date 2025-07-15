Work in Progress
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
