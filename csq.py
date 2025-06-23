#!/usr/bin/python
"""
This code is designed to work with the Telit ME910G1 modem connected via USB to
a Raspberry Pi.
"""
import re
import time
import serial
import serial.tools.list_ports

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
            # Check if 0x110a is the actual product ID of the device
            # For some reason, ttyUSB2 is the "good" port
            if port.vid == 0x1bc7 and port.pid == 0x110a and port.name.endswith("USB2"):
                self.chardev = port.device
                print(f"Detected Telit ME910G1 serial interface at {self.chardev}")
                break
            else:
                raise RuntimeError("Could not find the modem serial device")

        self.ser = serial.Serial(
            port=self.chardev,
            baudrate=baud,
            xonxoff=False,
            dsrdtr=True,
            timeout=timeout
        )

    # The write and query functions do not actually "open" the serial device.
    # This logic needs to be implemented in routines which use these methods.

    def AT_query(self, AT_commandline, timeout=0.05, silent=False):
        """Send an AT command and store the response.

        This method assumes the modem is using verbose result codes, those set
        by the command "ATV1". As an example, sending the command
        AT+CCLK?<CR>
        should result in a response similar to
        <CR><LF>+CCLK: "70/01/01,12:00:00"<CR><LF><CR><LF>OK<CR><LF>
        Visually, this may appear in a terminal as
        --------------------------
        AT+CCLK? (enter)
        +CCLK: "70/01/01,12:00:00"

        OK
        
        --------------------------
        Furthermore, at this moment there is no logic implemented to parse
        several information results, as may be the case of a commandline with
        more than one command.

        Args:
            AT_commandline (str): the AT commandline to send, with no carriage
                return or linebreak. Note that many commands require a SIM to
                be present.
            timeout (float): Amount of time in seconds to wait before
                reading the response.
            silent (bool): Whether to return the result, or return None.

        Returns: A string containing the modem's response, with OK, carriage
            returns, and line feeds stripped. Or, if no data is returned (other than an OK),
            returns None.
        """
        self.ser.reset_input_buffer()
        self.ser.write((AT_commandline+"\r").encode("ascii"))
        # need response to be mutable
        response = bytearray()
        time.sleep(timeout)
        while self.ser.in_waiting != 0:
            try:
                response.extend(self.ser.read(1))
            except serial.SerialException:
                raise RuntimeError("Failed to read from serial input buffer")

        response = response.decode("ascii")

        # handle response with actual data returned
        if "\r\n\r\n" in response:
            result, placeholder, result_code = response.rpartition("\r\n\r\n")
            parts = [i for i in map(str.strip, response.rpartition("\r\n\r\n"),
                                    ("\r\n",) * 3)]
            result = parts[0]
            result_code = parts[2]
        # handle response that is only "OK" or contains "ERROR"
        elif "\r\n" in response:
            result = None
            result_code = response.strip("\r\n")

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

        if result and not silent:
            return result
        # if the command only returns "OK" and no other information, do not return anything.
        else:
            return

    def setup(self):
        """Send an initialization AT commandline."""

        self.AT_query("AT V1 E1")

    # this method may be redundant
    def reset(self):
        """Send an AT commandline after done using the modem."""

        self.AT_query("ATZ")

    def self_test(self):
        """Check if the modem is responding to AT commands and more.

        In addition to the above, this routine checks if the SIM is inserted,
        GPS module is powered, and which LTE UE category is in use. There
        should be no commands in this routine which require SIM presence.
        """
        # serial.Serial has a context manager :)
        with self.ser:
            self.AT_query("AT")

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
            technology = self.AT_query("AT#WS46?")[-3]
            match technology:
                case "0":
                    print("LTE mode is CAT-M1")
                case "1":
                    print("LTE mode is NB-IoT")
                case "2":
                    print("LTE mode is CAT-M1 (preferred) and NB-IoT")
                case "3":
                    print("LTE mode is CAT-M1 and NB-IoT (preferred)")

            # Network registration status
            regstat = self.AT_query("AT+CREG?")[-1]
            match regstat:
                case "0":
                    print("Not registered, not searching for operator")
                case "1":
                    print("Registered on home network")
                case "2":
                    print("Not registered, searching for operator")
                case "3":
                    print("Registration denied")
                case "4":
                    print("Registration status unknown")
                case "5":
                    print("Registered, roaming")

            # Selected operator
            cops = self.AT_query("AT+COPS?")
            cops_mode = cops[7]
            match cops_mode:
                case "0":
                    print("Automatic operator selection")
                case "1":
                    print("Manual operator selection")
                case "2":
                    print("Deregistered from network")
                case "3":
                    pass
                case "4":
                    print("Manual operator selection, with automatic fallback")
            # If the module is not registered, there will only be one value reported.
            if "," in cops:
                cops_format = cops[9]
                cops_oper = cops[11]
                cops_act = cops[13]
                match cops_act:
                    case "0":
                        cops_act_human_readable = "GSM"
                    case "8":
                        cops_act_human_readable = "CAT M-1"
                    case "9":
                        cops_act_human_readable = "NB-IoT"
                print(f"Selected operator is {cops_oper} on mode {cops_act_human_readable}")
        
    def register(self, plmn, act="CAT M-1"):
        """Attempt to register on a cellular network.

        Args:
            plmn (int): The operator's Mobile Country Code followed by the
                Mobile Network code; the Public Land Mobile Network (PLMN) number.
            act (str): The access technology of the network. Either "CAT M-1"
                for LTE CAT M-1, or "NBIoT" for NBIoT.
        """
        with self.ser:
            pass
            if act.upper() in {"LTE CAT M-1", "LTE CAT M1", "CAT M-1", "CAT M1", "LTE-M", "LTE M"}:
                act = 8
            elif act.upper() in {"NBIOT", "NB-IOT", "NB IOT"}:
                act = 9

            self.AT_query(f"AT+COPS=1,2,{plmn},{act}")

    def network_test(self):
        """Get signal quality statistics.

        This method assumes that the modem is already registered on a cellular
        network.
        """
        csq = self.AT_query("AT+CSQ")
        servinfo = self.AT_query("AT#SERVINFO")

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
        cops_response = self.AT_query("AT+COPS=?", timeout=60)

        # This requires a connection to be established
        #print("Getting signal quality statistics...")
        #csq_response = self.AT_query("AT+CSQ")

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

if __name__ == "__main__":
    # here I'm planning to put the instantiation and data export code
    pass
