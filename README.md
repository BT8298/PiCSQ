# Overview
A set of python modules and scripts used in measuring LTE-M and NB-IoT network connection parameters.
Written as part of the Interactive Qualifying Project at Worcester Polytechnic Institute.
This software is designed for and tested on a Raspberry Pi Zero 2 board, with
- Sixfab 3G/4G & LTE Base HAT
- Telit ME910G1 (mPCIe)
- Waveshare Sense HAT (B)

as peripherals.
See also the webserver component of this project at https://github.com/asabramson/sensor-hat-transmission.
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
