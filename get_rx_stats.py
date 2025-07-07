#!/usr/bin/python
import os
import time
import datetime
#import re
import csv
import csq

modem = csq.TelitME910G1()
# temporary deregistration for testing; and runtime priority GNSS
# with modem.ser:
#    modem.AT_query("AT+COPS=2;$GPSCFG=3,0", silent=True)
# Print some diagnostic information
modem.self_test()
modem.sim_test()
# 30 seconds to fix
#modem.await_gnss(tries=10, interval=3)
lat="test"
lon="test"

# "Oneshot" datapoints; these are acquired only once when the script is run.
with modem.ser:
    # temporarily disabled via triple quote
    """
    gnss_sentence = modem.AT_query("AT$GPSACP")
    if gnss_sentence != (",,,,,0,,,,," or ",,,,,1,,,,,"):
        gnss_values = gnss_sentence.replace("$GPSACP: ", "").split(sep=",")
        year = "20" + gnss_values[9][4:6]
        month = gnss_values[9][2:4]
        day = gnss_values[9][0:2]
        date = datetime.date(year, month, day)

        degrees = gnss_values[1][0:2]
        minutes = gnss_values[1][2:4]
        decimal_minutes = gnss_values[1][5:9]
        # Convert latitude to decimal degrees format
        lat = degrees + minutes/60 + decimal_minutes/10000/60
        if gnss_values[1][-1] == "S":
            lat *= -1
        degrees = gnss_values[2][0:3]
        minutes = gnss_values[2][3:5]
        decimal_minutes = gnss_values[2][6:10]
        lon = degrees + minutes/60 + decimal_minutes/10000/60
        if gnss_values[2][-1] == "W":
            lon *= -1
        else:
            raise RuntimeWarning("Unable to acquire location via GNSS")
    """
    #m = re.search(r"(\d{6}\.\d{4}),(\d{4}\.\d{4}[NS]),(\d{5}\.\d{4}[EW]),(?:.+,){6}(\d{6})", gnss_sentence)
    #if m:
    #    year = int(m.group(4)[0:2])
    #    month = int(m.group(4)[2:4])
    #    day = int(m.group(4)[4:6])
    #    date = datetime.date(year, month, day).isoformat()
    #    # Latitude format is ddmm.mmmmN/S; convert to decimal degrees (+ is N)
    #    degrees = int(m.group(2)[0:2])
    #    minutes = int(m.group(2)[2:4])
    #    decimal_minutes = int(m.group(2)[5:9])
    #    # use convert to degrees-only format (e.g. 41.352566 degrees north)
    #    lat = degrees + minutes/60 + decimal_minutes/10000/60
    #    if m.group(2)[-1] == "S":
    #        lat *= -1
    #    # Longitude format is dddmm.mmmmE/W (yes, 3 digits for degrees); convert to decimal degrees (+ is E)
    #    degrees = int(m.group(3)[0:3])
    #    minutes = int(m.group(3)[3:5])
    #    decimal_minutes = int(m.group(3)[6:10])
    #    # degrees-only format
    #    lon = degrees + minutes/60 + decimal_minutes/10000/60
    #    if m.group(3)[-1] == "W":
    #        lat *= -1
    #else:
    #    raise RuntimeWarning('Unable to match regexp to "AT$GPSACP" response')

    # Set operator format to alphanumeric long form (up to 16 characters)
    # Can the following be merged into a single commandline?
    # selected_operator = modem.AT_query("AT+COPS=3,0;+COPS?")
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

    #m = re.fullmatch(r'\+COPS: \d,\d,"((\w|\s){1,16})",(\d)', cops_values)
    # m.group(1): op name
    # m.group(3): access technology
    #if m:
    #    operator_alphanumeric_name = m.group(1)
    #    match m.group(3):
    #        case "8":
    #            lte_ue_category = "M1"
    #        case "9":
    #            lte_ue_category = "NB1"
    #else:
        #raise RuntimeWarning('Modem is not registered with an operator, in GSM mode, or error in matching regexp to "AT+COPS?".')
    #    operator_alphanumeric_name = "N/A"
    #    lte_ue_category = "N/A"

#current_date_time = str(datetime.datetime.now().strftime("%m-%d-%Y_%H:%M:%S"))
#with open(f"{operator_alphanumeric_name}_LTE_CAT-{lte_ue_category}_{current_date_time}.csv", mode="w", newline="") as outfile:

filename = "signal_statistics.csv"
header = ["Trial", "Date", "Time", "Latitude (°)", "Longitude (°)", "LTE UE Category", "Operator Name", "PLMN", "EARFCN", "TAC", "RAC", "CELLID", "IMSI", "LTE BAND", "RSSI (dBm)", "RSRQ (dB)", "RSRP (dBm)", "SINR (dB)"]
with open(filename, mode="a", newline="") as outfile:
    writer = csv.DictWriter(outfile, header)
    if os.path.getsize(filename) == 0:
        writer.writeheader()
    # Number of trials to run
    trials = 3
    # How many seconds to wait before starting a new trial
    trial_interval = 30
    for i in range(1, trials+1):
        # Get time from GNSS
        print(f"Trial {i} of {trials} started")
        with modem.ser:
            gnss_sentence = modem.AT_query("AT$GPSACP")
            gnss_time = gnss_sentence.replace("$GPSACP: ", "").split(sep=",")[0]
            if len(gnss_time) == 10:
                utc_time = datetime.time(hour=int(gnss_time[0:2]),
                                         minute=int(gnss_time[2:4]),
                                         second=int(gnss_time[4:6]),
                                         tzinfo=datetime.timezone.utc)
            else:
                print("Could not determine time by GNSS, falling back to network-provided time")
                if modem.AT_query("AT+CTZU?")[-1] == "1":
                    # First element should be the date, second the time
                    # Assume the time is in UTC
                    rtc_date_time = modem.AT_query("AT+CCLK?").replace("+CCLK: ", "").strip('"').split(sep=",")
                    year = rtc_date_time[0][0:2]
                    month = rtc_date_time[0][3:5]
                    day = rtc_date_time[0][6:8]
                    date = datetime.date(int(year), int(month), int(day))
                    hour = rtc_date_time[1][0:2]
                    minute = rtc_date_time[1][3:5]
                    second = rtc_date_time[1][6:8]
                    utc_time = datetime.time(int(hour),int(minute), int(second), tzinfo=datetime.timezone.utc)
                else:
                    raise RuntimeWarning("Modem real-time clock is not configured to automatically update time")
        #m = re.search(r"(\d{6}\.\d{3}),", gnss_sentence)
        #if m:
        #    utc_time = datetime.time(hour=int(m.group(1)[0:2]),
        #                             minute=int(m.group(1)[2:4]),
        #                             second=int(m.group(1)[4:6]),
        #                             tzinfo=datetime.timezone.utc)
        #else:
        #    print("Could not determine time by GNSS, falling back to network-acquired time")
        #    if modem.AT_query("AT+CTZU?")[-1] == 1:
        #        # Should probably have AT+CCLKMODE=1 to report time in UTC
        #        # TODO: implement parsing logic
        #        utc_time = modem.AT_query("AT+CCLK?")
        signal_test_results = modem.signal_test()
        writer.writerow({"Trial": i,
                         "Date": date.isoformat(),
                         "Time": utc_time.strftime("%H:%M:%S"),
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
