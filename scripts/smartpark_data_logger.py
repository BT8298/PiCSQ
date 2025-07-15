#!/usr/bin/python
# Longrun systemd service which polls sensors, saves results to csv, and uploads most recent sensor values
import csv
import datetime
import grp
import json
import os
import pwd
import subprocess
import time
import warnings

import csq
import sensors

# Logging is done via printing to standard out, which is then caught by systemd-journald.

# Configuration
data_acquisition_interval = 15
unix_username = "wpi"
# Cannot use ~ expansion due to systemd not initializing HOME environment variable
csv_file_path = os.path.join(pwd.getpwnam(unix_username).pw_dir, "sensor_reading_history.csv")
# Either a domain name or IP address
website_address = "PUT_ADDRESS_HERE"
website_port = 80
# The resource to send to on the HTTP server
website_endpoint = "/api/sensordata"

SHTC3_sensor = sensors.SHTC3()
LPS22HB_sensor = sensors.LPS22HB()
modem = csq.TelitME910G1()

# think about how to identify which device this is and its location
csv_fields = ("Date (mm/dd/yy)", "Time (UTC)", "Temperature (°C)", "Relative Humidity (%)", "Pressure (hPa)")
with open("/etc/hostname", "r") as file:
    hostname = file.readline().strip("\r\n")

# Modem configuration and time acquisition
with modem.ser:
    # Report time in UTC and enable time updates from mobile network
    if modem.AT_query("AT#CCLKMODE?") != "#CCLKMODE: 1":
        modem.AT_query("AT#CCLKMODE=1")
    if modem.AT_query("AT+CTZU?") != "+CTZU: 1":
        modem.AT_query("AT+CTZU=1")
    cclk_response = modem.AT_query("AT+CCLK?").replace("+CCLK: ", "").strip('"')
    print(f"Received date and time from modem: {cclk_response}")
    modem.http_setup(server_address=website_address, server_port=website_port, pkt_size=100)
    modem.AT_query("AT#SGACT=1,1")

year = int(cclk_response[0:2])
month = int(cclk_response[3:5])
day = int(cclk_response[6:8])
hour = int(cclk_response[9:11])
minute = int(cclk_response[12:14])
second = int(cclk_response[15:17])
timedatectl_string = datetime.datetime(year, month, day, hour, minute, second, tzinfo=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

# unix_timestamp = datetime.datetime(year, month, day, hour, minute, second, tzinfo=datetime.timezone.utc).timestamp()
# need root to do this
# C library gives overflow error for July 2025 on pi zero 2 W; will need to use alternate method
# time.clock_settime(time.CLOCK_REALTIME, unix_timestamp)

# Workaround for datetime.datetime.timestamp() giving an overflow error (platform specific)
# Otherwise I would just use time.clock.settime(time.CLOCK_REALTIME, unix_timestamp)
if subprocess.run(("timedatectl", "set-timezone", "UTC", "--no-ask-password")).returncode != 0:
    raise RuntimeError("Failure in updating system timezone to UTC")
if subprocess.run(("timedatectl", "set-time", timedatectl_string, "--no-ask-password")).returncode != 0:
    raise RuntimeError("Failure in updating system clock")
else:
    print("System time updated")

# Set the process supplemental groups to dialout, to allow accessing
# /dev/ttyUSB devices
os.setgroups((grp.getgrnam("dialout").gr_gid,))
# Drop root priveleges needed for setting the system time
# This also ensures the csv file is accessible by the user
os.setgid(pwd.getpwnam(unix_username).pw_gid)
os.setuid(pwd.getpwnam(unix_username).pw_uid)

with open(csv_file_path, mode="a", newline="") as csvfile:
    print(f"Recording information to {csv_file_path}")
    writer = csv.DictWriter(csvfile, csv_fields)
    if os.stat(csv_file_path).st_size == 0:
        writer.writeheader()

while True:
    time_struct = time.gmtime(time.time())
    t_degrees_c, rh_percent = map(round, SHTC3_sensor.get_temperature_humidity(), (2,) * 2)
    p_hpa = round(LPS22HB_sensor.get_pressure(), 2)
    new_csv_row = {
                    "Date (mm/dd/yy)": time.strftime("%m/%d/%Y", time_struct),
                    "Time (UTC)": time.strftime("%H:%M:%S", time_struct),
                    "Temperature (°C)": t_degrees_c,
                    "Relative Humidity (%)": rh_percent,
                    "Pressure (hPa)": p_hpa
                  }
    print(f"New sensor reading: T {t_degrees_c} RH {rh_percent} P {p_hpa}")
    with open(csv_file_path, mode="a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, csv_fields)
        writer.writerow(new_csv_row)
    # Using one-letter variable names minimize size of data being transmitted
    # We set the last character of our device hostname to be a numeric identifier for the device
    json_data = json.dumps({"d": int(hostname[-1]), "t": t_degrees_c, "h": rh_percent, "p": p_hpa})
    # If the send interval is low enough (ballpark 5 seconds), I would
    # recommend keeping the serial device open instead of using the with
    # statement, which opens and closes the device each pass of the loop
    with modem.ser:
        try:
            modem.http_send(resource=website_endpoint, data=json_data, post_param="application/json")
        except csq.ATCommandError:
            warnings.warn("Exception in HTTP request", csq.ATCommandError)
    time.sleep(data_acquisition_interval)
