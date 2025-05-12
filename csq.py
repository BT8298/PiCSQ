#!/usr/bin/python
"""
This code is designed to work with the Telit ME910G1 modem connected via USB to
a Raspberry Pi.
"""
import sys
import re
import serial

# Used in pretty-printing results for diagnosticTest()
ws46_human_readable = (
        "CAT-M1",
        "NB-IoT",
        "CAT-M1 (preferred) and NB-IoT",
        "CAT-M1 and NB-IoT (preferred)"
        )
gpsp_human_readable = (
        "Off", "On"
        )
act_human_readable = {
        0: "GSM", 8: "CAT-M1", 9: "NB-IoT"
        }

for port in serial.tools.list_ports.comports():
    # check if 0x110a is the actual product ID of the device
    if port.vid == 0x1bc7 and port.pid == 0x110a:
        chardev = port.device
    else:
        print("Could not find the modem serial device.")
        sys.exit(1)

print(f"Detected Telit ME910G1 serial interface at {chardev}")

ser = serial.Serial(port=chardev, xonxoff=False, dsrdtr=True, timeout=3)


# The write and query functions do not actually open the serial device
def AT_write(AT_commandline):
    """
    ATCommandline (str): the AT commandline to send, with no carriage return or
    linebreak.
    """
    ser.write((AT_commandline+"\r").encode("utf-8"))


def AT_query(AT_commandline, custom_timeout=False):
    """
    AT_commandline (str): the AT commandline to send, with no carriage return
        or linebreak.
        Note that many commands require a SIM to be present.
    custom_timeout (int): override the default timeout in seconds for this
        query only.
    """
    # Default to the timeout specified by ser instantiation if not given
    # explicitly
    if custom_timeout:
        ser.timeout = custom_timeout
    ser.write((AT_commandline+"\r").encode("utf-8"))
    # Is the response really in UTF-8? Will have to look into this.
    response = ser.read_until(expected="\r").decode(encoding="utf-8")
    if custom_timeout:
        ser.timeout = 3
    return response


def diagnostic_test(display_result=False):
    """

    """
    ser.open()
    # Data Terminal Ready signal needs to be present for modem to work
    ser.dtr = 1

    # Check which LTE technology the modem is using.
    # Updates to this value take effect after reboot.
    print("Identifying current technology selection...")
    ws46_response = AT_query("AT#WS46?")

    print("Checking GPS module status...")
    gpsp_response = AT_query("AT$GPSP?")

    # Longer timeout due to network scan operation taking time
    print("Searching for available operators...")
    cops_response = AT_query("AT+COPS=?", custom_timeout=10)

    print("Getting signal quality statistics...")
    csq_response = AT_query("AT+CSQ")

    ser.dtr = 0
    ser.close()

    # Return format of AT+COPS=? is a string, with structure like
    # (status,alnum_long_name,,numeric_name,access_technology),(.,.,,.,.),...,,(.,.)
    # (yes, the double commas are intentional, according to Telit AT commands
    # manual {p. 187})
    # IDK what the last parenthesized expression means.
    # status (int): 0 - unknown. 1 - available. 2 - current. 3 - forbidden.
    # alnum_long_name (str): alphanumeric name of operator (16 char max.)
    # numeric_name (str): 5 or 6 digits, first 3 are country code, last are
    # network code (there should be double quotes around this value in
    # the response).
    # access_technology: 0 - GSM. 8 - CAT-M1. 9 - NB-IoT.
    operator_info = [eval(i.replace(",,", ",")) for i in re.findall(
        r'\([0123],"[\w &]{1,16}",,"[0-9]+",[089]\)', cops_response)]
    operators_available = []
    operator_current = "N/A"
    for i in operator_info:
        if i[0] == 1:
            # Convert numeric access technology type to human readable name
            operators_available.append(
                {"name": i[1], "code": i[2], "type": act_human_readable[i[3]]})
        if i[0] == 2:
            operator_current = {
                "name": i[1], "code": i[2], "type": act_human_readable[i[3]]}

    if display_result:
        print(
            "Preferred Technology: {}".format(
                ws46_human_readable[int(ws46_response[-1])]
                ),
            "GPS Power: {}".format(
                gpsp_human_readable[int(gpsp_response[-1])]
                                   ),
            "Current Network Operator: {}".format(operator_current),
            # "RSSI: {}".format(),
            # "BER: {}".format(),
            "Available Network Operators: \n{}".format(operators_available),
            sep="\n"
            )

    return {
            "WS46": ws46_response,
            "GPSP": gpsp_response,
            "COPS": cops_response,
            "CSQ": csq_response
            }
