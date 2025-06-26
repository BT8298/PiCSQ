#!/usr/bin/python
import os
import datetime
import re
import csv
import csq

modem = csq.TelitME910G1()
# temporary deregistration for testing; and runtime priority GNSS
with modem.ser:
    modem.AT_query("AT+COPS=2;$GPSCFG=3,0", silent=True)
# Print some diagnostic information
modem.self_test()
modem.sim_test()
# 30 seconds to fix
modem.await_gnss(tries=10, interval=3)

# "Oneshot" datapoints; these are acquired only once when the script is run.
with modem.ser:
    gnss_sentence = modem.AT_query("AT$GPSACP")
    m = re.search(r"(\d{6}\.\d{4}),(\d{4}\.\d{4}[NS]),(\d{5}\.\d{4}[EW]),(?:.+,){6}(\d{6})", gnss_sentence)
    if m:
        year = int(m.group(4)[0:2])
        month = int(m.group(4)[2:4])
        day = int(m.group(4)[4:6])
        date = datetime.date(year, month, day).isoformat()
        # Latitude format is ddmm.mmmmN/S; convert to decimal degrees (+ is N)
        degrees = int(m.group(2)[0:2])
        minutes = int(m.group(2)[2:4])
        decimal_minutes = int(m.group(2)[5:9])
        # use convert to degrees-only format (e.g. 41.352566 degrees north)
        lat = degrees + minutes/60 + decimal_minutes/10000/60
        if m.group(2)[-1] == "S":
            lat *= -1
        # Longitude format is dddmm.mmmmE/W (yes, 3 digits for degrees); convert to decimal degrees (+ is E)
        degrees = int(m.group(3)[0:3])
        minutes = int(m.group(3)[3:5])
        decimal_minutes = int(m.group(3)[6:10])
        # degrees-only format
        lon = degrees + minutes/60 + decimal_minutes/10000/60
        if m.group(3)[-1] == "W":
            lat *= -1
    else:
        raise RuntimeWarning('Unable to match regexp to "AT$GPSACP" response')

    # Set operator format to alphanumeric long form (up to 16 characters)
    # Can the following be merged into a single commandline?
    # selected_operator = modem.AT_query("AT+COPS=3,0;+COPS?")
    modem.AT_query("AT+COPS=3,0")
    cops_response = modem.AT_query("AT+COPS?")
    m = re.fullmatch(r'\+COPS: \d,\d,"((\w|\s){1,16})",(\d)', cops_response)
    # m.group(1): op name
    # m.group(3): access technology
    if m:
        operator_alphanumeric_name = m.group(1)
        match m.group(3):
            case "8":
                lte_ue_category = "M1"
            case "9":
                lte_ue_category = "NB1"
    else:
        #raise RuntimeWarning('Modem is not registered with an operator, in GSM mode, or error in matching regexp to "AT+COPS?".')
        operator_alphanumeric_name = "N/A"
        lte_ue_category = "N/A"

#current_date_time = str(datetime.datetime.now().strftime("%m-%d-%Y_%H:%M:%S"))
#with open(f"{operator_alphanumeric_name}_LTE_CAT-{lte_ue_category}_{current_date_time}.csv", mode="w", newline="") as outfile:

filename = "signal_statistics.csv"
header = ["Trial", "Date", "Time", "Latitude (°)", "Longitude (°)", "LTE UE Category", "Operator Name", "RSSI (dBm)"]
with open(filename, mode="a", newline="") as outfile:
    writer = csv.DictWriter(outfile, header)
    if os.path.getsize(filename) == 0:
        writer.writeheader()
    for i in range(1, 4):
        # Get time from GNSS
        with modem.ser:
            gnss_sentence = modem.AT_query("AT$GPSACP")
        m = re.search(r"(\d{6}\.\d{3}),", gnss_sentence)
        if m:
            utc_time = datetime.time(int(m.group(1)[0:2]),
                                     int(m.group(1)[2:4]),
                                     int(m.group(1)[4:6]),
                                     tzinfo=datetime.timezone.utc)
        else:
            raise RuntimeWarning("Could not determine time by GNSS, falling back to network-acquired time")
            # actually implement this fallback
            # warning seems to stop execution — not intentional.
        # uncomment when we activate the SIM
        #rssi = modem.signal_test()["rssi"]
        rssi = "N/A"
        writer.writerow({"Trial": i,
                         "Date": date,
                         "Time": utc_time.strftime("%H:%M:%S"),
                         "Latitude (°)": lat,
                         "Longitude (°)": lon,
                         "LTE UE Category": lte_ue_category,
                         "Operator Name": operator_alphanumeric_name,
                         "RSSI (dBm)": rssi})
