#!/usr/bin/python
import warnings
import os
import sys
import getopt
import argparse
import time
import datetime
#import re
import csv
import csq

# This script collects information from the modem and GNSS receiver into a CSV file.

parser = argparse.ArgumentParser()
parser.add_argument("-g", help="Attempt to get a GPS fix")
parser.add_argument("-o", nargs=2, default="signal_statistics.csv", help="The csv file in which to save the data. Defaults to %(default)s")
parser.add_argument("-t", nargs=2, default=3, help="The number of trials to run. Defaults to %(default)s")
parser.add_argument("-i", nargs=2, default=30, help="The number of seconds to wait in between trials. Defaults to %(default)s")
argns = parser.parse_args()

filename = argns.o if hasattr(argns, "o") else "signal_statistics.csv"
trials = int(argns.t) if hasattr(argns, "t") else 3
trial_interval = int(argns.i) if hasattr(argns, "i") else 30

modem = csq.TelitME910G1()
# Print some diagnostic information
modem.self_test()
modem.sim_test()
# Dummy values if GNSS fix not requested
lat="N/A"
lon="N/A"
# 30 seconds to fix
if hasattr(argns, "g"):
    modem.await_gnss(tries=10, interval=3)

# "Oneshot" datapoints; these are acquired only once when the script is run.
with modem.ser:
    gnss_sentence = modem.AT_query("AT$GPSACP")
    if gnss_sentence != (",,,,,0,,,,," or ",,,,,1,,,,,"):
        gnss_values = gnss_sentence.replace("$GPSACP: ", "").split(sep=",")
        year = 20 + int(gnss_values[9][4:6])
        month = int(gnss_values[9][2:4])
        day = int(gnss_values[9][0:2])
        date = datetime.date(year, month, day).isoformat()

        # Process latitude value
        degrees = gnss_values[1][0:2]
        minutes = gnss_values[1][2:4]
        decimal_minutes = gnss_values[1][5:9]
        # Convert latitude to decimal degrees format
        lat = degrees + minutes/60 + decimal_minutes/10000/60
        if gnss_values[1][-1] == "S":
            lat *= -1
        # Process longitude value
        degrees = gnss_values[2][0:3]
        minutes = gnss_values[2][3:5]
        decimal_minutes = gnss_values[2][6:10]
        lon = degrees + minutes/60 + decimal_minutes/10000/60
        if gnss_values[2][-1] == "W":
            lon *= -1
    else:
        warnings.warn("Unable to acquire location and date via GNSS; falling back to network-provided date", RuntimeWarning)

    if modem.AT_query("AT+CTZU?")[-1] == "1":
        rtc_date_time = modem.AT_query("AT+CCLK?").replace("+CCLK: ", "").strip('"').split(sep=",")
        year = 20 + int(rtc_date_time[0][0:2])
        month = int(rtc_date_time[0][3:5])
        day = int(rtc_date_time[0][6:8])
        date = datetime.date(year, month, day).isoformat()
    else:
        date = "N/A"
        warnings.warn("Modem real-time clock is not configured to automatically update date. Use manually recorded date instead!", RuntimeWarning)

    # Set operator format to alphanumeric long form (up to 16 characters)
    modem.AT_query("AT+COPS=3,0")
    cops_values = modem.AT_query("AT+COPS?").replace("+COPS: ", "").split(sep=",")
    # Check if the modem is registered with an operator
    if len(cops_values) > 1:
        operator_alphanumeric_name = cops_values[2].strip('"')
        match cops_values[3]:
            case "8":
                lte_ue_category = "M1"
            case "9":
                lte_ue_category = "NB1"
    elif len(cops_values) == 1:
        raise RuntimeError("The modem is not registered to a network")
    else:
        raise RuntimeError("Unknown error in \"AT+COPS?\" query")

# The CSV header
header = [
        "Trial",
        "Date",
        "Time",
        "Latitude (°)",
        "Longitude (°)",
        "LTE UE Category",
        "Operator Name",
        "PLMN",
        "EARFCN",
        "TAC",
        "RAC",
        "CELLID",
        "IMSI",
        "LTE BAND",
        "RSSI (dBm)",
        "RSRQ (dB)",
        "RSRP (dBm)",
        "SINR (dB)"
        ]

with open(filename, mode="a", newline="") as outfile:
    writer = csv.DictWriter(outfile, header)
    if os.path.getsize(filename) == 0:
        writer.writeheader()

    for i in range(1, trials+1):
        # Get time from GNSS, with network time fallback
        print(f"Trial {i} of {trials} started")
        with modem.ser:
            gnss_sentence = modem.AT_query("AT$GPSACP")
            gnss_time = gnss_sentence.replace("$GPSACP: ", "").split(sep=",")[0]
            if len(gnss_time) == 10:
                hour = int(gnss_time[0:2])
                minute = int(gnss_time[2:4])
                second = int(gnss_time[4:6])
                utc_time = datetime.time(hour, minute, second,
                                         tzinfo=datetime.timezone.utc).strftime("%H:%M:%S")
            else:
                print("Could not determine time by GNSS, falling back to network-provided time")
                if modem.AT_query("AT+CTZU?")[-1] == "1":
                    # First element should be the date, second the time
                    # Assume the time is in UTC
                    rtc_date_time = modem.AT_query("AT+CCLK?").replace("+CCLK: ", "").strip('"').split(sep=",")
                    hour = int(rtc_date_time[1][0:2])
                    minute = int(rtc_date_time[1][3:5])
                    second = int(rtc_date_time[1][6:8])
                    utc_time = datetime.time(hour, minute, second,
                                             tzinfo=datetime.timezone.utc).strftime("%H:%M:%S")
                else:
                    utc_time = "N/A"
                    warnings.warn("Modem real-time clock is not configured to automatically update time. Use manually recorded time instead!", RuntimeWarning)

        signal_test_results = modem.signal_test()
        writer.writerow({"Trial": i,
                         "Date": date,
                         "Time": utc_time,
                         "Latitude (°)": lat,
                         "Longitude (°)": lon,
                         "LTE UE Category": lte_ue_category,
                         "Operator Name": signal_test_results["opname"],
                         "PLMN": signal_test_results["plmn"],
                         "EARFCN": signal_test_results["earfcn"],
                         "TAC": signal_test_results["tac"],
                         "RAC": signal_test_results["rac"],
                         "CELLID": signal_test_results["cellid"],
                         # This is the International Mobile Station Identity,
                         # not subscriber identity.
                         "IMSI": signal_test_results["imsi"],
                         "LTE BAND": signal_test_results["abnd"],
                         "RSSI (dBm)": signal_test_results["rssi"],
                         "RSRQ (dB)": signal_test_results["rsrq"],
                         "RSRP (dBm)": signal_test_results["rsrp"],
                         "SINR (dB)": signal_test_results["sinr"]})

        print(f"Trial {i} of {trials} ended. Waiting {trial_interval} seconds to start next trial.")
        time.sleep(trial_interval)
