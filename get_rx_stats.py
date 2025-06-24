#!/usr/bin/python
import datetime
import re
import csv
import csq

modem = csq.TelitME910G1()
# Print some diagnostic information
modem.self_test()
modem.sim_test()
# 30 seconds to fix
modem.await_gnss(tries=10, interval=3)

# Acquire position only once, but time will be acquired for each trial.
gnss_sentence = modem.AT_query("AT$GPSACP")
# re.match is appropriate - need the first 3 anyway
m = re.match(r"(\d{6}\.\d{3}),(\d{4}\.\d{4}[NS]),(\d{5}\.\d{4}[EW])", gnss_sentence)

if m:
    #utc_time = datetime.time(int(m.group(1)[0:2]),
    #                         int(m.group(1)[2:4]),
    #                         int(m.group(1)[4:6]),
    #                         tzinfo=datetime.timezone.utc)
    # Latitude format is ddmm.mmmmN/S; convert to decimal degrees (+ is N)
    lat = sum(int(m.group(2)[0:2]),
              int(m.group(2)[2:4])/60,
              int(m.group(2)[5:9])/10000/60)
    if m.group(2)[-1] == "S":
        lat *= -1
    # Longitude format is dddmm.mmmmE/W (yes, 3 digits for degrees); convert to decimal degrees (+ is E)
    lon = sum(int(m.group(3)[0:3]),
              int(m.group(3)[3:5])/60,
              int(m.group(3)[6:10])/10000/60)
    if m.group(3)[-1] == "W":
        lat *= -1

# Set operator format to alphanumeric long form (up to 16 characters)
# Can the following be merged into a single commandline?
# selected_operator = modem.AT_query("AT+COPS=3,0;+COPS?")
modem.AT_query("AT+COPS=3,0")
selected_operator = modem.AT_query("AT+COPS?")

m = re.fullmatch(r'\+COPS: \d,\d,"((\w|\s){1,16})",(\d)', selected_operator)
m.group(1)  # op name
m.group(3)  # access technology

if m:
    operator_alphanumeric_name = m.group(1)
    match m.group(3):
        case "8":
            lte_ue_category = "M1"
        case "9":
            lte_ue_category = "NB1"
else:
    raise RuntimeError("Modem is not registered with an operator (or it is in GSM mode).")

current_date_time = str(datetime.datetime.now().strftime("%m-%d-%Y_%H:%M:%S"))

# File format example:
# Verizon_LTE_CAT-M1_03-20-2025_08:53:06.csv
with open(f"{operator_alphanumeric_name}_LTE_CAT-{lte_ue_category}_{current_date_time}.csv", mode="w", newline="") as outfile:
    writer = csv.DictWriter(outfile, ("Trial", "Time", "Latitude (°)",
                                      "Longitude (°)", "RSSI (dBm)"))
    writer.writeheader()
    for i in range(1, 4):
        # get gps time
        gnss_sentence = modem.AT_query("AT$GPSACP")
        m = re.match(r"(\d{6}\.\d{3}),", gnss_sentence)
        if m:
            utc_time = datetime.time(int(m.group(1)[0:2]),
                                     int(m.group(1)[2:4]),
                                     int(m.group(1)[4:6]),
                                     tzinfo=datetime.timezone.utc)
        else:
            raise RuntimeWarning("Could not determine time by GNSS, falling back to network-acquired time")
            # actually implement this fallback
        # uncomment when we activate the SIM
        #rssi = modem.signal_test()["rssi"]
        writer.writerow({"Trial": i,
                         "Time": utc_time.strftime("%H:%M:%S"),
                         "Latitude (°)": lat,
                         "Longitude (°)": lon,
                         "RSSI (dBm)": rssi})
