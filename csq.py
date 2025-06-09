#!/usr/bin/python
"""
This code is designed to work with the Telit ME910G1 modem connected via USB to
a Raspberry Pi.
"""
import re
import serial
import serial.tools.list_ports

# Used in pretty-printing results for diagnostic_test()
ws46_human_readable = (
    "CAT-M1",
    "NB-IoT",
    "CAT-M1 (preferred) and NB-IoT",
    "CAT-M1 and NB-IoT (preferred)"
)
gpsp_human_readable = (
    "Off",
    "On"
)
cops_act_human_readable = {
    0: "GSM",
    8: "CAT-M1",
    9: "NB-IoT"
}


class TelitME910G1:
    """Interact with a Telit ME910G1 cellular modem.

    The modem is designed for LTE UE categories NB1/2 and M1.
    """

    def __init__(self, baud=115200, timeout=3):
        """Autodetect the modem and set serial link parameters.

        The last modem found is initialized (we assume there is only one modem
        connected at a time).
        """
        for port in serial.tools.list_ports.comports():
            # check if 0x110a is the actual product ID of the device
            if port.vid == 0x1bc7 and port.pid == 0x110a:
                chardev = port.device
            else:
                raise RuntimeError("Could not find the modem serial device")

        print(f"Detected Telit ME910G1 serial interface at {chardev}")

        self.ser = serial.Serial(
            port=chardev,
            baudrate=baud,
            xonxoff=False,
            dsrdtr=True,
            timeout=timeout
        )

    # The write and query functions do not actually "open" the serial device.
    # This logic needs to be implemented in routines which use these methods.
    def AT_write(self, AT_commandline):
        """Send an AT command and check for errors.

        This method flushes the serial input buffer.

        AT_commandline (str): the AT commandline to send, with no carriage
            return or linebreak.
        """
        self.ser.reset_input_buffer()
        self.ser.write((AT_commandline+"\r").encode("ascii"))
        response = bytearray()
        while self.ser.in_waiting != 0:
            try:
                response.extend(self.ser.read(1))
            except serial.SerialException:
                raise RuntimeError("Failed to read from serial input buffer")

        result_code = response.decode("ascii")
        if "OK" in result_code:
            return
        elif "ERROR" in result_code:
            err_msg = result_code.replace("\r\n", "")
            raise RuntimeError(
                f'Command "{AT_commandline}" resulted in error "{err_msg}"')
        else:
            raise RuntimeError(
                'Modem did not send response to command '
                f'"{AT_commandline}", '
                'or there was an error reading it (a timeout?)'
            )

    def AT_query(self, AT_commandline, custom_timeout=False):
        """Send an AT command and store the response.

        This method assumes the modem is using verbose result codes, those set
        by the command "ATV1". As an example, sending the command
        AT+CCLK?<CR>
        should result in a response similar to
        <CR><LF>+CCLK: "70/01/01,12:00:00"<CR><LF><CR><LF>OK<CR><LF>
        Visually, this may appear in a terminal as
        ---------------------------------
        user@hostname:~$ AT+CCLK? (enter)
        +CCLK: "70/01/01,12:00:00"

        OK
        user@hostname:~$
        ---------------------------------
        Furthermore, at this moment there is no logic implemented to parse
        several information results, as may be the case of a commandline with
        more than one command.

        Args:
            AT_commandline (str): the AT commandline to send, with no carriage
                return or linebreak. Note that many commands require a SIM to
                be present.
            custom_timeout (int): override the default timeout in seconds
                for this query only.

        Returns: A string containing the modem's response.
        """
        # Default to the timeout specified by ser instantiation if not given
        # explicitly
        if custom_timeout:
            self.ser.timeout = custom_timeout

        self.ser.write((AT_commandline+"\r").encode("ascii"))
        # need response to be mutable
        response = bytearray()
        while self.ser.in_waiting != 0:
            try:
                response.extend(self.ser.read(1))
            except serial.SerialException:
                raise RuntimeError("Failed to read from serial input buffer")

        response = response.decode("ascii")
        result, placeholder, result_code = response.rpartition("\r\n\r\n")
        # first element is the data response, second is "",
        # third is result code ("OK", "ERROR", etc)
        parts = [i for i in map(str.strip, response.rpartition("\r\n\r\n"),
                                ("\r\n",) * 3)]
        result = parts[0]
        result_code = parts[2]

        # check result code first
        if "OK" in result_code:
            pass
        elif "ERROR" in result_code:
            raise RuntimeError(
                f'Command "{AT_commandline}" resulted in error "{result_code}"')
        else:
            raise RuntimeError(
                'Modem did not send result code to command '
                f'"{AT_commandline}", '
                'or there was an error reading it (a timeout?)'
            )

        if custom_timeout:
            self.ser.timeout = 3

        return result

    def self_test(self):
        """Check if the modem is responding to AT commands and more.

        In addition to the above, this routine checks if the SIM is inserted,
        GPS module is powered, and which LTE UE category is in use. There
        should be no commands in this routine which require SIM presence.
        """
        # serial.Serial has a context manager :)
        with self.ser:
            if self.AT_query("AT") != "OK":
                raise RuntimeError("Modem did not respond \"OK\" to \"AT\"")

            # query sim status
            sim_status = self.AT_query("AT#QSS?")[-1]

            # match statement was added in python 3.10
            match sim_status:
                case "0":
                    raise RuntimeWarning("SIM not inserted")
                case "1":
                    print("SIM inserted")
                case "2":
                    print("SIM is PIN-unlocked")
                case "3":
                    print("SIM is ready")
                case _:
                    raise RuntimeError("Unable to determine SIM status")

            # GPS power
            gps_power = self.AT_query("AT$GPSP?")[-1]
            match gps_power:
                case "0":
                    print("GNSS controller is powered off")
                case "1":
                    print("GNSS controller is powered on")
                case _:
                    raise RuntimeError("Unable to determine GPS power state")

    def sim_test(self):
        """Show results of various SIM-required AT commands.

        This routine displays the selected LTE UE category (NB-IoT or CAT M1),
        . There should be no commands in this routine which require network
        registration.
        """
        with self.ser:
            # IoT technology (NB-IoT or M1)
            technology = self.AT_query("AT#WS46?")[-1]  # string type
            match technology:
                case "0":
                    print("LTE mode is CAT-M1")
                case "1":
                    print("LTE mode is NB-IoT")
                case "2":
                    print("LTE mode is CAT-M1 (preferred) and NB-IoT")
                case "3":
                    print("LTE mode is CAT-M1 and NB-IoT (preferred)")
                case _:
                    raise RuntimeError("Unable to determine IoT technology")

    def register(self, act="NB-IoT"):
        """Attempt to register on the Verizon network."""
        with self.ser:
            pass
            # WIP
            # self.AT_write("AT+COPS=

    def diagnostic_test(self, display_result=False):
        """Acquire various LTE parameters and optionally print to stdout.

        Args:
            display_result (bool): Whether to print the results in a
                human-readable format.

        Returns: Dictionary with keys the name of the command sent. The
            available keys are "WS46", "GPSP", "COPS", and "CSQ".
        """
        self.ser.open()
        # Data Terminal Ready signal needs to be present for modem to work.
        # Per the documentation, this seems to be handled by the open method.
        # self.ser.dtr = 1

        # Check which LTE technology the modem is using.
        # Updates to this value take effect after reboot.
        print("Identifying current technology selection...")
        ws46_response = self.AT_query("AT#WS46?")

        print("Checking GPS module status...")
        gpsp_response = self.AT_query("AT$GPSP?")

        # Longer timeout due to network scan operation taking time
        print("Searching for available operators...")
        cops_response = self.AT_query("AT+COPS=?", custom_timeout=10)

        print("Getting signal quality statistics...")
        csq_response = self.AT_query("AT+CSQ")

        # MAYBE ADD???
        # Below code parses out the rssi_code from csq_response
        # Double check on the specific conversion formula (this one is typical for Telit products), info should be in the user manual once we unpackage it
        # We may want to edit the function to also return this dBm value, as it is the best marker of signal strength (which is the main purpose of the script from what I can tell)


        # raw = csq_response[-1]                  # e.g. "+CSQ: 23,99"
        # m = re.match(r"\+CSQ:\s*([0-9]+),", raw)
        # if m:
        #     rssi_code = int(m.group(1))         # e.g. 23
        #     # per typical Telit formula: dBm = –113 + 2 × RSSI_code
        #     rssi_dbm = -113 + (2 * rssi_code)   # e.g. –113 + 46 = –67 dBm
        # else:
        #     rssi_code = None
        #     rssi_dbm = None

        # print(f"Parsed RSSI: code={rssi_code}, approx {rssi_dbm} dBm")



        # self.ser.dtr = 0
        self.ser.close()

        # Return format of AT+COPS=? is a string, with structure like
        # (status,alnum_long_name,,numeric_name,access_technology),(.,.,,.,.),...,,(.,.)
        # (yes, the double commas are intentional, according to Telit AT
        # commands manual {p. 187})
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
            # status: available
            if i[0] == 1:
                # Convert numeric access technology type to human readable name
                operators_available.append(
                    {
                        "name": i[1],
                        "code": i[2],
                        "type": cops_act_human_readable[i[3]]
                    }
                )
            # status: current
            if i[0] == 2:
                operator_current = {
                    "name": i[1],
                    "code": i[2],
                    "type": cops_act_human_readable[i[3]]
                }

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
                "Available Network Operators: \n{}".format(
                    operators_available),
                sep="\n"
            )

        return {
            "WS46": ws46_response,
            "GPSP": gpsp_response,
            "COPS": cops_response,
            "CSQ": csq_response
        }
