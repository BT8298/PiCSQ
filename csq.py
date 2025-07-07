"""AT command wrapper for TelitME910G1.

This code is designed to work with the Telit ME910G1 modem connected via USB to
a Raspberry Pi.
"""
import warnings
#import re
import time
import serial
import serial.tools.list_ports
import RPi.GPIO as rgp


class SixfabBaseHat:
    """Interface to GPIO features of the board."""

    def __init__(self):
        rgp.setmode(rgp.BOARD)
        # LED line
        rgp.setup(13, rgp.OUT, initial=rgp.LOW)
        # Airplane mode
        rgp.setup(35, rgp.OUT, initial=rgp.LOW)
        # Board poweroff
        rgp.setup(37, rgp.OUT, initial=rgp.LOW)

    @property
    def led(self):
        return True if rgp.input(13) == 1 else False

    @led.setter
    def led(self, state):
        if state in {1, True, "on"}:
            rgp.output(13, rgp.HIGH)
        elif state in {0, False, "off"}:
            rgp.output(13, rgp.LOW)

    @property
    def airplane_mode(self):
        return True if rgp.input(35) == 1 else False

    @airplane_mode.setter
    def airplane_mode(self, state):
        if state in {1, True, "on"}:
            rgp.output(35, rgp.HIGH)
        elif state in {0, False, "off"}:
            rgp.output(35, rgp.LOW)

    @property
    def power(self):
        """Control the power to the HAT.

        True if the HAT is powered; False if not.
        """
        return False if rgp.input(37) == 1 else True

    @power.setter
    def power(self, state):
        if state in {1, True, "on"}:
            rgp.output(37, rgp.LOW)
        elif state in {0, False, "off"}:
            rgp.output(37, rgp.HIGH)


class TelitME910G1(SixfabBaseHat):
    """Interact with a Telit ME910G1 cellular modem.

    The modem is designed for LTE UE categories NB1/2 and M1.
    """

    def __init__(self, baud=115200, timeout=0.1):
        """Autodetect the modem and set serial link parameters.

        The last modem found is initialized (we assume there is only one modem
        connected at a time).
        """
        super().__init__()
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

        with self.ser:
            self.AT_query("ATE0Q0V1X0&S3&K3+IFC=2,2;+CMEE=2")
        # This will not run again if the modem is powered off via the parent
        # class!

    # The write and query functions do not actually "open" the serial device.
    # This logic needs to be implemented in routines which use these methods.

    def parse_csurv(self, AT_response):
        # First element should be "\r\nNetwork survey started ..."
        # Last elements should be "Network survey ended" and "OK"
        scan_results = AT_response.split(sep="\r\n\r\n")
        result_code = scan_results[-1]
        # Check if any operators were found
        if len(scan_results) - 3 != 0:
            # A list of lines representing scanned operators
            result = scan_results[1:len(scan_results) - 2]
        else:
            result = None
        return result, result_code

    def AT_query(self, AT_commandline, timeout=None, wait=0.1, silent=False):
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
            timeout (float): Temporary override for serial read timeout, in
                seconds.
            wait (float): Duration of the time to wait between checking for
                received data, in seconds.
            silent (bool): Whether to return the result, or return None.

        Returns: A string containing the modem's response, with OK, carriage
            returns, and line feeds stripped. Or, if no data is returned (other
            than an OK), returns None. If the AT command was AT#CSURV, then the
            response is a list of operators found by the scan, and if none were
            found, returns None.
        """
        # Set timeout override
        if timeout:
            old_timeout = self.timeout
            setattr(self.ser, "timeout", timeout)
        # Clear input buffer
        if self.ser.in_waiting != 0:
            self.ser.reset_input_buffer()
        # Somewhere I saw it was recommended to wait 50ms before sending next
        # command
        time.sleep(0.05)
        self.ser.write((AT_commandline+"\r").encode("ascii"))
        # wait for response, if it takes long; for example, AT+COPS=?
        while self.ser.in_waiting == 0:
            time.sleep(wait)
        # need response to be mutable
        response = bytearray()
        while self.ser.in_waiting != 0:
            try:
                response.extend(self.ser.read(1))
            except serial.SerialException:
                raise RuntimeError("Failed to read from serial input buffer")
        # Restore original timeout
        if timeout:
            setattr(self.ser, "timeout", old_timeout)

        response = response.decode("ascii")

        # Handle response with actual data returned.
        # Designed for only a single data response; no chaining AT commands in
        # a single line
        if "#CSURV" in AT_commandline.upper():
            result, result_code = self.parse_csurv(response)
        elif "\r\n\r\n" in response:
            result, placeholder, result_code = response.rpartition("\r\n\r\n")
            parts = [i for i in map(str.strip, response.rpartition("\r\n\r\n"),
                                    ("\r\n",) * 3)]
            result = parts[0]
            result_code = parts[2]
        # Handle response that is only "OK" or contains "ERROR"
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
        # if the command only returns "OK" and no other information, do not
        # return anything.
        else:
            return

    def one_time_setup(self):
        # These settings need to be saved into a profile via AT&W
        # Command Echo Off: E0
        # Execution Result Messages (e.g. "OK"): Q0
        # Verbose Error Messages: V1
        # Minimal Extended Result Codes: X0
        # Assert DSR When Ready to Receive AT Commands: &S3
        # Use RTS/CTS: &K3
        # Use RTS/CTS (alternate): +IFC=2,2
        # Use CME ERROR messages: +CMEE=2
        # Automatically update real time clock via network: AT+CTZU=1
        # Save to profile 0: AT&W0
        self.AT_query("ATE0Q0V1X0&S3&K3+IFC=2,2;+CMEE=2;+CTZU=1;&W0", silent=True)

        # These settings are automatically saved to the non-volatile memory
        # Two USB interfaces for AT commands: AT#PORTCFG=8
        # USB modem ports, 1 diag port, 1 WWAN adapter (no data traffic): AT#USBCFG=0
        # Set DTR manually or raise on incoming bytes: AT#DTR=2
        # Prefer LTE-M over NB-IoT: AT#WS46=2
        # Disable NB2 mode: AT#NB2ENA=0
        # Use all available bands: AT#BND=5,0,252582047,0,1048578
        # Report time via AT+CCLK? in UTC: AT#CCLKMODE=1
        self.AT_query("AT#PORTCFG=8;AT#USBCFG=0;AT#DTR=2;AT#WS46=2;AT#NB2ENA=0;AT#BND=5,0,252582047,0,1048578;#CCLKMODE=1",
                      silent=True)

        # These commands have a custom way of saving to NVM.
        # Auto select GNSS constellation depending on MCC: AT$GPSCFG=2,0
        # Prioritize WWAN over GNSS at runtime: AT$GPSCFG=3,1
        # GNSS power on: AT$GPSP=1
        # Save GNSS settings in NVM: AT$GPSSAV
        self.AT_query("AT$GPSCFG=2,0;$GPSCFG=3,1;$GPSP=1;$GPSSAV", silent=True)

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
                    warnings.warn("SIM not inserted", RuntimeWarning)
                case "1":
                    print("SIM inserted")
                case "2":
                    print("SIM is PIN-unlocked")
                case "3":
                    print("SIM is ready")

            # GPS power
            gps_power = self.AT_query("AT$GPSP?")[-1]
            match gps_power:
                case "0":
                    print("GNSS controller powered off")
                case "1":
                    print("GNSS controller powered on")

    def await_gnss(self, tries=10, interval=1):
        """Turn on the GNSS unit and await a fix.

        Args:
            tries (int): The number of times to query the GNSS unit for a fix
                before giving up.
            interval (float): The time in seconds to wait between each query
                for the GNSS fix.
        """
        with self.ser:
            if self.AT_query("AT$GPSP?")[-1] == "0":
                self.AT_query("AT$GPSP=1")
            i = 1
            while self.AT_query("AT$GPSACP") in {"$GPSACP: ,,,,,0,,,,,", "$GPSACP: ,,,,,1,,,,,"}:
                if i > tries:
                    raise RuntimeWarning(f"Could not acquire GNSS fix in {tries} tries ({tries*interval} seconds)")
                    #warnings.warn(f"Could not acquire GNSS fix in {tries} tries ({tries*interval} seconds)", RuntimeWarning)
                    break
                print(f"GNSS fix attempt: {i}")
                time.sleep(interval)
                i += 1

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
            cops_values = self.AT_query("AT+COPS?").replace("+COPS: ", "").split(sep=",")
            cops_mode = cops_values[0]
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
            # If the module is not registered, there will only be one value
            # reported.
            if len(cops_values) > 1:
                cops_format = cops_values[1]
                cops_oper = cops_values[2]
                cops_act = cops_values[3]
                match cops_act:
                    case "0":
                        cops_act_human_readable = "GSM"
                    case "8":
                        cops_act_human_readable = "CAT M-1"
                    case "9":
                        cops_act_human_readable = "NB-IoT"
                print(f"Selected operator is {cops_oper} on mode {cops_act_human_readable}")

    #def register(self, plmn, act="CAT M-1"):
    #    """Attempt to register on a cellular network.

    #    Args:
    #        plmn (int): The operator's Mobile Country Code followed by the
    #            Mobile Network code; the Public Land Mobile Network (PLMN)
    #            number.
    #        act (str): The access technology of the network. Either "CAT M-1"
    #            for LTE CAT M-1, or "NBIoT" for NBIoT.
    #    """
    #    with self.ser:
    #        if act.upper() in {"LTE CAT M-1", "LTE CAT M1", "CAT M-1", "CAT M1", "LTE-M", "LTE M"}:
    #            act = 8
    #        elif act.upper() in {"NBIOT", "NB-IOT", "NB IOT"}:
    #            act = 9

    #        self.AT_query(f"AT+COPS=1,2,{plmn},{act}")

    def signal_test(self):
        """Get signal quality statistics.

        This method assumes that the modem is already registered on a cellular
        network.
        """
        with self.ser:
            rfsts = self.AT_query("AT#RFSTS")

            # Check if modem is registered on a network
            if self.AT_query("AT+COPS?").count(",") != 0:
                sstats = rfsts.replace("#RFSTS: ", "").split(sep=",")
                # "imsi" key is the International Mobile Station Identity, not to be
                # confused with subscriber identity.
                return {"plmn": sstats[0].strip('"'), "earfcn": sstats[1], "rsrp": sstats[2],
                        "rssi": sstats[3], "rsrq": sstats[4], "tac": sstats[5],
                        "rac": sstats[6], "cellid": sstats[11], "imsi": sstats[12].strip('"'),
                        "opname": sstats[13].strip('"'), "abnd": sstats[15], "sinr":
                        sstats[18]}
            else:
                warnings.warn("Modem is not registered on a network", RuntimeWarning)

        #m = re.match(r"\+CSQ:\s*([0-9]+),", csq)
        #if m:
        #    rssi_code = int(m.group(1))         # e.g. 23
        #    # per typical Telit formula: dBm = –113 + 2 × RSSI_code
        #    rssi_dbm = -113 + (2 * rssi_code)   # e.g. –113 + 46 = –67 dBm
        #else:
        #    rssi_code = None
        #    rssi_dbm = None

        #print(f"Parsed RSSI: code={rssi_code}, approx {rssi_dbm} dBm")

        #return {"rssi": rssi_dbm, "rssi_raw": rssi_code}

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

if __name__ == "__main__":
    # here I'm planning to put the instantiation and data export code
    pass
