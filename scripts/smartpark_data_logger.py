#!/usr/bin/python
# Longrun systemd service which polls sensors, saves results to csv, and uploads most recent sensor values
import csv
import datetime
#import logging
import os
import pathlib
import pwd
import subprocess
import time

import csq
import sensors

# Let's just call it a day and make everything a print statement, to be caught by systemd-journald
# logger = logging.getLogger(__name__)
# logger.debug("Logger initialized")
# print("Logger initialized")

# Configuration
csv_file_path = pathlib.PosixPath("~wpi/sensor_reading_history.csv").expanduser()
data_acquisition_interval = 15
unix_username = "wpi"

SHTC3_sensor = sensors.SHTC3()
LPS22HB_sensor = sensors.LPS22HB()
modem = csq.TelitME910G1()

# add periodic time sync via at+cclk? to pi rtc

# think about how to identify which device this is and its location
csv_fields = ("Date", "Time (UTC)", "Temperature (°C)", "Relative Humidity (%)", "Pressure (hPa)")

# update rtc routine here
with modem.ser:
    # Report time in UTC and enable time updates from mobile network
    if modem.AT_query("AT#CCLKMODE?") != "#CCLKMODE: 1":
        modem.AT_query("AT#CCLKMODE=1")
    if modem.AT_query("AT+CTZU?") != "+CTZU: 1":
        modem.AT_query("AT+CTZU=1")
    cclk_response = modem.AT_query("AT+CCLK?").replace("+CCLK: ", "").strip('"')
    #logger.info(f"Got time from modem: {cclk_response}")
    print(f"Received date and time from modem: {cclk_response}")
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
    subprocess.run(("timedatectl", "set-timezone", "UTC", "--no-ask-password"))
    subprocess.run(("timedatectl", "set-time", timedatectl_string, "--no-ask-password"))

# Drop root priveleges needed for setting the system time
# This also ensures the csv file is accessible by the user
os.setgid(pwd.getpwnam(unix_username).pw_gid)
os.setuid(pwd.getpwnam(unix_username).pw_uid)

# chmod and chgrp to wpi; or use suid sgid?
with open(csv_file_path, mode="a", newline="") as csvfile:
    #logger.info(f"Recording information to {str(csv_file_path)}")
    print(f"Recording information to {str(csv_file_path)}")
    writer = csv.DictWriter(csvfile, csv_fields)
    if csv_file_path.stat().st_size == 0:
        writer.writeheader()
        #logger.debug(f"Wrote header line to file {str(csv_file_path)}")
        print(f"Wrote header line to file {str(csv_file_path)}")

    # implement SIGTERM handling?
    while True:
        time_struct = time.gmtime(time.time())
        date = time.strftime("%m/%d/20%y", time_struct)
        utc_time = time.strftime("%H:%M:%S", time_struct)
        temp, hum = map(round, SHTC3_sensor.get_temperature_humidity(), (2,) * 2)
        press = round(LPS22HB_sensor.get_pressure(), 2)
        print(f"Temperature: {temp} °C, Relative Humidity: {hum}%, Pressure: {press} hPa")
        writer.writerow({
                        "Date": date,
                        "Time (UTC)": utc_time,
                        "Temperature (°C)": temp,
                        "Relative Humidity (%)": hum,
                        "Pressure (hPa)": press
                        })
        # network code here
        time.sleep(data_acquisition_interval)
