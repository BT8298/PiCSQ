"""AT command wrapper for TelitME910G1.

This code is designed to work with the Telit ME910G1 modem connected via USB to
a Raspberry Pi.
"""
import datetime
import io
import re
import time
import warnings

import serial
import serial.tools.list_ports
import RPi.GPIO as rgp


class SixfabBaseHat:
    """Interface to GPIO features of the Sixfab 3G/4G Base HAT."""

    def __init__(self):
        rgp.setmode(rgp.BCM)
        # User LED initially off
        rgp.setup(27, rgp.OUT, initial=rgp.LOW)
        # Airplane mode initially off
        rgp.setup(19, rgp.OUT, initial=rgp.LOW)
        # Power to HAT; keep same state as before (low is on, high is cut off)
        rgp.setup(26, rgp.OUT, initial=None)

    @property
    def led(self):
        return True if rgp.input(13) == 1 else False

    @led.setter
    def led(self, state):
        if state in {1, True, "on"}:
            #rgp.output(13, rgp.HIGH)
            rgp.output(27, rgp.HIGH)
        elif state in {0, False, "off"}:
            #rgp.output(13, rgp.LOW)
            rgp.output(27, rgp.LOW)

    @property
    def airplane_mode(self):
        return True if rgp.input(19) == 1 else False

    @airplane_mode.setter
    def airplane_mode(self, state):
        if state in {1, True, "on"}:
            rgp.output(19, rgp.HIGH)
        elif state in {0, False, "off"}:
            rgp.output(19, rgp.LOW)

    @property
    def power(self):
        """Control the power to the HAT.

        True if the HAT is powered; False if not.
        """
        return False if rgp.input(26) == 1 else True

    @power.setter
    def power(self, state):
        if state in {1, True, "on"}:
            rgp.output(26, rgp.LOW)
        elif state in {0, False, "off"}:
            rgp.output(26, rgp.HIGH)


class ModemError(RuntimeError):
    """An error relating to modem communication."""
    pass


class ATCommandError(ModemError):
    """An error reported by an AT command result code."""
    pass


class ModemWarning(RuntimeWarning):
    """A warning related to modem communication."""
    pass


class ATCommandWarning(RuntimeWarning):
    """A warning related to the result of an AT command.

    For example, this is used to notify the user when the GNSS position
    acquisition command succesfully executes, but returns no coordinates (did
    not acquire fix yet).
    """
    pass


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
        self.power = True
        # To turn on ME910G1, a certain pad must be tied low for at least 5
        # seconds, then released. Refer to Telit ME910G1 Hardware Design Guide
        # document.
        print("DEBUG waiting 5 seconds for module power-on")
        time.sleep(5)
        for port in serial.tools.list_ports.comports():
            # Check if 0x110a is the actual product ID of the device
            # For some reason, ttyUSB2 is the "good" port
            if port.vid == 0x1bc7 and port.pid == 0x110a:
                self.chardev = port.device
                print(f"Detected Telit ME910G1 serial interface at {self.chardev}")
                break
            else:
                raise RuntimeError("Could not detect the modem serial port")

        self.ser = serial.Serial(
            port=self.chardev,
            baudrate=baud,
            xonxoff=False,
            dsrdtr=True,
            timeout=timeout
        )

        self.sio = io.TextIOWrapper(io.BufferedRWPair(self.ser, self.ser), newline="", line_buffering=True)

        # At initial startup, the modem hangs waiting when trying to get
        # response to these. Wait 3 seconds as a lazy workaround.
        time.sleep(3)
        with self.ser:
            self.cmd_query("ATE0Q0V1X0&S3&K3")
            self.cmd_query("AT+IFC=2,2;+CMEE=2")
        # This will not run again if the modem is powered off via the parent
        # class!

    def parse_gpsacp(self, AT_response):
        """Parse the results of AT$GPSACP."""
        if AT_response != (",,,,,0,,,,," or ",,,,,1,,,,,"):
            gnss_values = AT_response.replace("$GPSACP: ", "").split(sep=",")
            # Process date
            year = int("20" + gnss_values[9][4:6])
            month = int(gnss_values[9][2:4])
            day = int(gnss_values[9][0:2])
            date = datetime.date(year, month, day).isoformat()
            # Process UTC time
            hour = int(gnss_values[0][0:2])
            minute = int(gnss_values[0][2:4])
            second = int(gnss_values[0][4:6])
            time = datetime.time(hour, minute, second,
                                     tzinfo=datetime.timezone.utc).strftime("%H:%M:%S")
            # Process latitude
            degrees = int(gnss_values[1][0:2])
            minutes = int(gnss_values[1][2:4])
            decimal_minutes = int(gnss_values[1][5:9])
            # Convert latitude to decimal degrees format
            lat = degrees + minutes/60 + decimal_minutes/10000/60
            if gnss_values[1][-1] == "S":
                lat *= -1
            # Process longitude
            degrees = int(gnss_values[2][0:3])
            minutes = int(gnss_values[2][3:5])
            decimal_minutes = int(gnss_values[2][6:10])
            lon = degrees + minutes/60 + decimal_minutes/10000/60
            if gnss_values[2][-1] == "W":
                lon *= -1
        else:
            warnings.warn("No GNSS fix yet; falling back to network-provided date", ATCommandWarning)
            lat = "N/A"
            lon = "N/A"
            date, time = self.parse_cclk(self.cmd_query("AT+CCLK?"))

        return date, time, lat, lon

    def parse_cclk(self, AT_response):
        """Return formatted date and time by reading modem clock.

        Args:
            AT_response (str): The information response returned by AT+CCLK?; for
                example: '+CCLK: "02/09/07,22:30:25"'
        """
        modem_date_time = AT_response.replace("+CCLK: ", "").strip('"').split(sep=",")
        # Process date
        year = int("20" + modem_date_time[0][0:2])
        month = int(modem_date_time[0][3:5])
        day = int(modem_date_time[0][6:8])
        date = datetime.date(year, month, day).isoformat()
        # Process time, assumed to be in UTC
        # Checking and setting modem time reporting to UTC should be done
        # outside of this function, which is purely a parser
        hour = int(modem_date_time[1][0:2])
        minute = int(modem_date_time[1][3:5])
        second = int(modem_date_time[1][6:8])
        time = datetime.time(hour, minute, second,
                                 tzinfo=datetime.timezone.utc).strftime("%H:%M:%S")

        return date, time

    def parse_csurv(self, AT_response_lines):
        """Parser for the results of AT#CSURV.

        AT#CSURV is manufacturer-specific network survey command.
        Args:
            AT_response_lines (list|tuple): A list of lines returned by
            AT#CSURV, not including the result code. This argument should
            include the initial "Network survey started ..." and the final
            "Network survey ended" lines.

        Returns:
            A tuple of cell info results, with each result being a dictionary
            having keys "EARFCN", "MCC", "MNC", "ACT", "PCI", "TAC", "ECI".
            These are (respectively) the Evolved Absolute Radio Frequency
            Number, Mobile Country Code, Mobile Network Code, Access Technology
            (one of NB-IoT or LTE-M), Physical Cell Identifier, Tracking Area
            Code, and E-UTRAN Cell Identifier.
        """
        # Strip network survey started and ended lines
        AT_response_lines = AT_response_lines[1:len(AT_response_lines) - 1]
        network_info_list = []
        for network in AT_response_lines:
            # Use regex here since the some of the values can be padded with
            # spaces, so str.split won't work.
            # Also some of the values can either be in decimal or hexadecimal,
            # hence the \w rather than \d
            m = re.match(r'earfcn: (?: *)(\d{1,5}) rxLev: 0 mcc: (\d{3}) mnc: (\d{2,3}) (?:NBIoT)cellid: (?: *)(\w+) tac: (?: *      )(\w+) cellIdentity: (?: *)(\w+) rsrp: 0.00 rsrq: 0.00', flags=re.ASCII)
            if "NBIoT" in m.group(0):
                act = "NB-IoT"
            else:
                act = "LTE-M"
            network_info_list.append({
                "EARFCN": m.group(1),
                "MCC": m.group(2),
                "MNC": m.group(3),
                "ACT": act,
                "PCI": m.group(4),
                "TAC": m.group(5),
                "ECI": m.group(6)
                })

        return network_info_list

    def await_urc(self, timeout=3, wait=0.1):
        old_timeout = self.ser.timeout
        self.ser.timeout = timeout
        # hint is 5 so that it can capture '\r\nOK\r\n' but nothing longer
        URC = self.sio.readlines(5)[1].strip('\r\n')
        self.ser.timeout = old_timeout

        if URC == '':
            warnings.warn('Timeout in waiting for URC', ModemWarning)
        return URC

    def cmd_query(self, AT_commandline, timeout=None, wait=0.1, multiline=False):
        # This method assumes the serial device is already opened via serial.Serial.open() method.
        # Currently this is buggy with AT#HTTPRCV, due to delayed OK
        """Send an AT command, and receive a response.

        Args:
            AT_commandline (str): The AT commandline to send to the modem,
                without carriage return. This can be more than one command, for
                example, AT+CREG=1;+COPS=0.
            timeout (float): Temporary override for the serial device timeout,
                in seconds. Default None.
            wait (float): How long to wait, in seconds, until checking the
                serial buffer for new bytes when expecting a response. Default
                0.1.
            multiline (bool): Whether the response will contain multiple lines
                (excluding result codes). If True, the return type will be an
                array of lines. Default False.

        Returns: Either a string containing the data response (if no data, it
            is the empty string) or an array of strings representing a line in
            the response, if multiline was True.

        Write about custom return for AT#HTTPRCV
        """
        # Set read timeout override
        if timeout:
            old_timeout = self.ser.timeout
            setattr(self.ser, "timeout", timeout)

        if self.ser.in_waiting != 0:
            self.ser.reset_input_buffer()
        # Telit recommends waiting 20ms between commands
        time.sleep(0.02)
        self.sio.write(AT_commandline+"\r")

        # User LED indicates waiting for AT response
        self.led = True
        while self.ser.in_waiting == 0:
            time.sleep(wait)
        self.led = False

        response_lines = []
        print("DEBUG serial buffer has", self.ser.in_waiting, "bytes in waiting")
        response_lines = self.sio.readlines()
        print("DEBUG read all lines in serial buffer")
        print("DEBUG serial buffer has", self.ser.in_waiting, "bytes in waiting")
        print("DEBUG BufferedRWPair buffer has", len(self.sio.buffer.peek()), "bytes in waiting")
        print("DEBUG the lines read are", response_lines)

        # Custom parsing for HTTP responses
        if AT_commandline.upper().startswith('AT#HTTPRCV'):
            old_timeout = self.ser.timeout
            self.ser.timeout = 0.5
            # Check for '\r\nOK\r\n'
            # hint is 5; will read '\r\n' and then '\r\nOK' making total size 6, which exceeds 5
            result_code = ''.join(self.sio.readlines(5)).replace('\r\n', '')
            self.ser.timeout = old_timeout
            if result_code == "OK":
                http_response = ''.join(response_lines)
                # For some reason not working?
                #http_response = http_response.removeprefix('\r\n>>>')
                http_response = http_response[5:]
                return http_response
            elif "ERROR" in result_code:
                raise ATCommandError(f'Command "{AT_commandline}" returned result code "{result_code}"')

        for line in response_lines:
            if line in {'\r\n', ''}:
                response_lines.remove(line)
        # I tried doing this in a single for loop, and did not get desired
        # result.
        for line in response_lines:
            if '\r\n' in line:
                response_lines[response_lines.index(line)] = line.strip('\r\n')
        print("DEBUG processed response lines is now", response_lines)

        # Error checking
        result_code = response_lines.pop()
        if "OK" in result_code:
            pass
        elif "ERROR" in result_code:
            raise ATCommandError(f'Command "{AT_commandline}" returned result code "{result_code}"')
        # NO CARRIER appears to be used by Telit to signal when a socket is
        # closed Also, AT#SGACTCFGEXT has an option to enable sending 1 byte
        # before AT#SGACT=n,1 completes, to abort PDP context activation. NO
        # CARRIER is sent as confirmation.
        elif "NO CARRIER" in result_code:
            raise ATCommandError(f'Command "{AT_commandline}" returned "NO CARRIER"')
        # I don't think I've ever seen this one
        #elif "CONNECT" in result_code:
        #    pass
        else:
            raise ModemError('No result code detected for "{AT_commandline}", or there was an error reading it')

        # Restore original timeout
        #TODO this doesnt seem to work
        if timeout:
            setattr(self.ser, "timeout", old_timeout)

        if multiline:
            return response_lines
        elif not multiline and len(response_lines) != 0:
            return response_lines[0]
        else:
            return ''

    def one_time_setup(self):
        """One-time configuration.

        This method sets various parameters in the modem and saves them to
        non-volatile memory.
        """
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
        self.cmd_query("ATE0Q0V1X0&S3&K3+IFC=2,2;+CMEE=2;+CTZU=1;&W0")

        # These settings are automatically saved to the non-volatile memory
        # Two USB interfaces for AT commands: AT#PORTCFG=8
        # USB modem ports, 1 diag, 1 WWAN (no data traffic): AT#USBCFG=0
        # Set DTR manually or raise on incoming bytes: AT#DTR=2
        # Prefer LTE-M over NB-IoT: AT#WS46=2
        # Disable NB2 mode: AT#NB2ENA=0
        # Use all available bands: AT#BND=5,0,252582047,0,1048578
        # Report time via AT+CCLK? in UTC: AT#CCLKMODE=1
        # Configure PDP context APN: AT+CGDCONT=1,IP,soracom.io,"",1,1
        # Configure PDP context authentication: AT+CGAUTH=1,2,sora,sora
        self.cmd_query("AT#PORTCFG=8;"
                       "#USBCFG=0;"
                       "#DTR=2;"
                       "#WS46=2;"
                       "#NB2ENA=0;"
                       "#BND=5,0,252582047,0,1048578;"
                       "#CCLKMODE=1;"
                       '+CGDCONT=1,IP,soracom.io,"",1,1;'
                       "+CGAUTH=1,2,sora,sora",
                       )

        # These commands have a custom way of saving to NVM.
        # Auto select GNSS constellation depending on MCC: AT$GPSCFG=2,0
        # Prioritize WWAN over GNSS at runtime: AT$GPSCFG=3,1
        # GNSS power off: AT$GPSP=0
        # Save GNSS settings in NVM: AT$GPSSAV
        self.cmd_query("AT$GPSCFG=2,0;"
                       "$GPSCFG=3,1;"
                       "$GPSP=0;"
                       "$GPSSAV",
                       )

    # Maybe ECM mode is better...
    def http_setup(self, server_address, http_prof_id=0, server_port=80,
                   pkt_size=300, http_response_timeout=30, pdp_cid=1):
        """Save an HTTP context to the non-volatile memory of the modem.

        This is for HTTP, not HTTPS.

        Args:
            server_address (str): The IP address or domain name of the remote
                server to connect to.
            http_prof_id (int|str): The numeric profile identifier (0 to 2) to
                save this context to; default 0.
            server_port (int|str): The listening port of the remote server;
                default 80.
            pkt_size (int|str): Unsure of what this is, but ranges from 1 to
                1500; default 300.
            http_response_timeout (int|str): Timeout for the server's response.
            pdp_cid (int|str): ID of the PDP context (1 to modem-specific
                maximum number) to use for this HTTP context; default 1.
        """
        self.cmd_query(f"AT#HTTPCFG="
                       f"{http_prof_id},"
                       f"{server_address},"
                       f"{server_port},"
                       # No HTTP authentication, username, password, or SSL.
                       '0,"","",0,'
                       f"{http_response_timeout},"
                       f"{pdp_cid},"
                       f"{pkt_size},"
                       "0,0",
                       )

    def http_send(self, resource, data, http_prof_id=0, request_type="POST", post_param=1, wait=0.1):
        """Send an HTTP request to a remote endpoint.

        Args:
            resource (str): The HTTP resource to send the request to. Must
                always begin with "/"; for example, to send to
                "www.foo.bar/api/intake", resource should be set to
                "/api/intake".
            data (str): The data to send in the body of the request. Currently
                the type must be str.
            http_prof_id (int|str): The numeric identifier (from 0 to 2) of the
                HTTP context to use; default 0. These are stored on the modem
                non-volatile memory.
            request_type (str): Either "POST" or "PUT".
            post_param (str): The HTTP Content-type; defaults to
            "application/x-www-form-urlencoded". Only use with POST requests.
            wait (float):

        """
        match request_type.upper():
            case "POST":
                command = 0
            case "PUT":
                command = 1
            case _:
                raise RuntimeError("Unsupported request_type")

        if command == 0:
            HTTP_AT_command = "AT#HTTPSND=" \
                              f"{http_prof_id}," \
                              f"{command}," \
                              f"{resource}," \
                              f"{len(data)}"
        elif command == 1:
            HTTP_AT_command = "AT#HTTPSND=" \
                              f"{http_prof_id}," \
                              f"{command}," \
                              f"{resource}," \
                              f"{len(data)}," \
                              f"{post_param}"

        print("DEBUG about to send:", HTTP_AT_command)

        # Just like self.cmd_query, the serial device needs to be opened by
        # a higher level piece of code
        if self.ser.in_waiting != 0:
            self.ser.reset_input_buffer()

        time.sleep(0.05)
        self.sio.write(HTTP_AT_command+"\r")

        self.led = True
        while self.ser.in_waiting == 0:
            time.sleep(0.1)
        self.led = False

        try:
            # Should be "\r\n>>>"
            ready_for_data_entry = self.sio.read(5)
        except serial.SerialException:
            raise serial.SerialException("Failed to read from serial input buffer; expected \">>>\" (ready for data entry for HTTP request)")

        print("DEBUG ready_for_data_entry is", "'" + ready_for_data_entry.replace('\r\n', '\\r\\n') + "'")

        if ready_for_data_entry != "\r\n>>>":
            raise ModemError(f"Modem returned {ready_for_data_entry} when \"\\r\\n>>>\" was expected")
        else:
            self.sio.write(data)
            self.sio.flush()

            self.led = True
            while self.ser.in_waiting == 0:
                time.sleep(wait)
            self.led = False
            # Check for <CR><LF>OK<CR><LF>
            result_code = self.sio.readlines(5)
            print("DEBUG result code after AT#HTTPSND is", result_code)
            if "OK\r\n" not in result_code:
                raise ATCommandError(f"Modem returned error after attempting to send HTTP data: {result_code}")

            return

    def self_test(self):
        """Check if the modem is responding to AT commands and more.

        In addition to the above, this routine checks if the SIM is inserted,
        GPS module is powered, and which LTE UE category is in use. There
        should be no commands in this routine which require SIM presence.
        """
        # serial.Serial has a context manager :)
        with self.ser:
            self.cmd_query("AT")

            # query sim status
            sim_status = self.cmd_query("AT#QSS?")[-1]

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
            gps_power = self.cmd_query("AT$GPSP?")[-1]
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
            if self.cmd_query("AT$GPSP?")[-1] == "0":
                self.cmd_query("AT$GPSP=1")
            i = 1
            while self.cmd_query("AT$GPSACP") in {"$GPSACP: ,,,,,0,,,,,", "$GPSACP: ,,,,,1,,,,,"}:
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
            technology = self.cmd_query("AT#WS46?")[-3]
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
            regstat = self.cmd_query("AT+CREG?")[-1]
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
            cops_values = self.cmd_query("AT+COPS?").replace("+COPS: ", "").split(sep=",")
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

    def signal_test(self):
        """Get signal quality statistics.

        This method assumes that the modem is already registered on a cellular
        network.
        """
        with self.ser:
            rfsts = self.cmd_query("AT#RFSTS")

            # Check if modem is registered on a network
            if self.cmd_query("AT+COPS?").count(",") != 0:
                sstats = rfsts.replace("#RFSTS: ", "").split(sep=",")
                return {"plmn": sstats[0].strip('"'), "earfcn": sstats[1], "rsrp": sstats[2],
                        "rssi": sstats[3], "rsrq": sstats[4], "tac": sstats[5],
                        "rac": sstats[6], "cellid": sstats[11], "imsi": sstats[12].strip('"'),
                        "opname": sstats[13].strip('"'), "abnd": sstats[15], "sinr":
                        sstats[18]}
            else:
                warnings.warn("Modem is not registered on a network", RuntimeWarning)
