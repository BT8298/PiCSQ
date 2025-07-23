#!/usr/bin/python
import warnings
import os
import argparse
import time
import csv
import csq

parser = argparse.ArgumentParser()
parser.add_argument("-g", action="store_true", help="Attempt to get a GPS fix")
parser.add_argument("-o", type=str, default="signal_statistics.csv", help="The csv file in which to save the data. Defaults to %(default)s")
parser.add_argument("-t", type=int, default=3, help="The number of trials to run. Defaults to %(default)s")
parser.add_argument("-i", type=float, default=30, help="The number of seconds to wait in between trials. Defaults to %(default)s")
argns = parser.parse_args()

filename = argns.o
trials = argns.t
trial_interval = argns.i

modem = csq.TelitME910G1()
# Print some diagnostic information
modem.self_test()
modem.sim_test()
# 30 seconds to fix
_GNSS_fix = False
if argns.g:
    try:
        modem.await_gnss(tries=10, interval=3)
        _GNSS_fix = True
    except RuntimeWarning:
        print("Unable to acquire GNSS fix")
        _GNSS_fix = False

# "Oneshot" datapoints; these are acquired only once when the script is run.
with modem.ser:
    if modem.AT_query("AT+CTZU?")[-1] == "1":
        _network_time_up_to_date = True
    # Only execute this chunk if GNSS has a fix
    if _GNSS_fix:
        date, _, lat, lon = modem.parse_gpsacp(modem.AT_query("AT$GPSACP"))
        warnings.warn("Unable to acquire location and date via GNSS; falling back to network-provided date", RuntimeWarning)
    elif _network_time_up_to_date:
        print("Using WWAN for time and date instead of GNSS")
        date, _ = modem.parse_cclk(modem.AT_query("AT+CCLK?"))
        lat = "N/A"
        lon = "N/A"
    else:
        date = "N/A"
        warnings.warn("Modem real-time clock is not configured to automatically update. Use manually recorded time information instead!", RuntimeWarning)

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
        "Date",
        "Time (UTC)",
        "Latitude (°)",
        "Longitude (°)",
        "LTE UE Category",
        "Operator Name",
        "PLMN",
        "EARFCN",
        "TAC",
        "RAC",
        "CELLID",
        "LTE BAND",
        "RSSI (dBm)",
        "RSRP (dBm)",
        "RSRQ (dB)",
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
            # Run this chunk if GNSS has a fix
            _use_network_time = True
            if _GNSS_fix:
                _, utc_time, _, _, = modem.parse_gpsacp(modem.AT_query("AT$GPSACP"))
            elif _network_time_up_to_date:
                # Assume the time is in UTC
                _, utc_time = modem.parse_cclk(modem.AT_query("AT+CCLK?"))
            else:
                utc_time = "N/A"

        signal_test_results = modem.signal_test()
        writer.writerow({"Date": date,
                         "Time (UTC)": utc_time,
                         "Latitude (°)": lat,
                         "Longitude (°)": lon,
                         "LTE UE Category": lte_ue_category,
                         "Operator Name": signal_test_results["opname"],
                         "PLMN": signal_test_results["plmn"],
                         "EARFCN": signal_test_results["earfcn"],
                         "TAC": signal_test_results["tac"],
                         "RAC": signal_test_results["rac"],
                         "CELLID": signal_test_results["cellid"],
                         "LTE BAND": signal_test_results["abnd"],
                         "RSSI (dBm)": signal_test_results["rssi"],
                         "RSRP (dBm)": signal_test_results["rsrp"],
                         "RSRQ (dB)": signal_test_results["rsrq"],
                         "SINR (dB)": signal_test_results["sinr"]})

        print(f"Trial {i} of {trials} ended")
        if trials > 1 and i < trials:
            print(f"Waiting {trial_interval} seconds to start next trial")
            time.sleep(trial_interval)
