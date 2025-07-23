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


class ModemError(RuntimeError):
    """An error relating to modem communication."""
    pass


class ATCommandError(ModemError):
    """An error reported by an AT command result code."""
    pass


class ModemWarning(RuntimeWarning):
    pass


class ATCommandWarning(RuntimeWarning):
    """Warning related to the result of an AT command.

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

        with self.ser:
            self.cmd_query("ATE0Q0V1X0&S3&K3")
            self.cmd_query("AT+IFC=2,2;+CMEE=2")
        # This will not run again if the modem is powered off via the parent
        # class!

    # The write and query functions do not actually "open" the serial device.
    # This logic needs to be implemented in routines which use these methods.

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
            A tuple of cell info results, with each result being a dictionary having keys "EARFCN", "MCC", "MNC", "ACT", "PCI", "TAC", "ECI". These are (respectively) the Evolved Absolute Radio Frequency Number, Mobile Country Code, Mobile Network Code, Access Technology (one of NB-IoT or LTE-M), Physical Cell Identifier, Tracking Area Code, and E-UTRAN Cell Identifier.
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
        # Currently this is buggy with AT#HTTPRCV, due to delayed OK
        """TODO

        Write about the normal return
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

        while self.ser.in_waiting == 0:
            time.sleep(wait)

        response_lines = []
        # TextIOWrapper.readline consumes up to io.DEFAULT_BUFFER_SIZE bytes
        # from the serial buffer, so checking serial.Serial.in_waiting is not
        # reliable after a single call to readline.
        # Instead, check the BufferedReader's buffer without actually emptying
        # it via io.BufferedReader.peek to see if there is anything left there.
        # IT SEEMS THAT THE BufferedReader's BUFFER IS ALSO COMPLETELY EMPTIED UPON A SINGLE readline()
        # Also io.DEFAULT_BUFFER_SIZE appears to be 8192 on Raspbian.
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
        # result
        for line in response_lines:
            if '\r\n' in line:
                response_lines[response_lines.index(line)] = line.strip('\r\n')
        print("DEBUG processed response lines is now", response_lines)
        #while len(self.sio.buffer.peek()) != 0:
        #    incoming_line = self.sio.readline()
        #    print("DEBUG read new line:", incoming_line.replace('\r\n', '\\r\\n'))
        #    print("DEBUG TextIOWrapper buffer now has", len(self.sio.buffer.peek()), "bytes in waiting")
        #    if incoming_line not in {'\r\n', ''}:
        #        response_lines.append(incoming_line.strip('\r\n'))
        #    elif incoming_line == '':
        #        break

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
        #elif "NO CARRIER" in result_code:
        #    raise ATCommandError(f'Command ')
        ## I don't think I've ever seen this one
        #elif "CONNECT" in result_code:
        #    pass
        else:
            raise ModemError('No result code detected for "{AT_commandline}", or there was an error reading it')

        # Restore original timeout
        #TODO this doesnt seem to work
        if timeout:
            setattr(self.ser, "timeout", old_timeout)

        if multiline:
            # Return each line except the result code, which was popped from
            # the list earlier
            return response_lines
        elif not multiline and len(response_lines) != 0:
            return response_lines[0]
        else:
            return ''

    # DEPRECATED
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
            old_timeout = self.ser.timeout
            setattr(self.ser, "timeout", timeout)
        # Clear input buffer
        if self.ser.in_waiting != 0:
            self.ser.reset_input_buffer()
        # Telit recommends waiting 20ms before issuing subsequent command
        time.sleep(0.02)
        self.ser.write((AT_commandline+"\r").encode("ascii"))
        # wait for response, if it takes long; for example, AT+COPS=?
        while self.ser.in_waiting == 0:
            time.sleep(wait)
        # need response to be mutable
        response = bytearray()
        while self.ser.in_waiting != 0:
                response.extend(self.ser.read(1))
        # Restore original timeout
        if timeout:
            setattr(self.ser, "timeout", old_timeout)

        response = response.decode("ascii")

        # Handle a single information response and result code
        # Designed for only a single data response; do not chain AT commands
        # that have more than one information response in a single line
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
            raise ATCommandError(f'Command "{AT_commandline}" returned "{result_code}"')
        # NO CARRIER appears to be used by Telit to signal when a socket is
        # closed Also, AT#SGACTCFGEXT has an option to enable sending 1 byte
        # before AT#SGACT=n,1 completes, to abort PDP context activation. NO
        # CARRIER is sent as confirmation.
        #elif "NO CARRIER" in result_code:
        #    raise ATCommandError(f'Command ')
        ## I don't think I've ever seen this one
        #elif "CONNECT" in result_code:
        #    pass
        else:
            raise ModemError('Modem did not send result code to command "{AT_commandline}", or there was an error reading it (a timeout?)')

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
        self.cmd_query("ATE0Q0V1X0&S3&K3+IFC=2,2;+CMEE=2;+CTZU=1;&W0", silent=True)

        # These settings are automatically saved to the non-volatile memory
        # Two USB interfaces for AT commands: AT#PORTCFG=8
        # USB modem ports, 1 diag port, 1 WWAN adapter (no data traffic): AT#USBCFG=0
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
                      silent=True)

        # These commands have a custom way of saving to NVM.
        # Auto select GNSS constellation depending on MCC: AT$GPSCFG=2,0
        # Prioritize WWAN over GNSS at runtime: AT$GPSCFG=3,1
        # GNSS power on: AT$GPSP=1
        # Save GNSS settings in NVM: AT$GPSSAV
        self.cmd_query("AT$GPSCFG=2,0;"
                      "$GPSCFG=3,1;"
                      "$GPSP=1;"
                      "$GPSSAV",
                      silent=True)

    # Maybe ECM mode is better...
    def http_setup(self, server_address, http_prof_id=0, server_port=80,
                   pkt_size=300, http_response_timeout=30, pdp_cid=1):
        """Save an HTTP context to the non-volatile memory of the modem.

        This is for HTTP, not HTTPS.

        Args:
            server_address (str): The IP address or domain name of the remote
                server to connect to.
            prof_id (int|str): The numeric profile identifier (0 to 2) to save
                this context to; default 0.
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

        print("DEBUG HTTP_AT_command is", HTTP_AT_command)

        # Just like self.cmd_query, the serial device needs to be opened by
        # a higher level piece of code
        if self.ser.in_waiting != 0:
            self.ser.reset_input_buffer()

        time.sleep(0.05)
        self.sio.write(HTTP_AT_command+"\r")

        # Sometimes the modem just disconnects the USB link (kernel says GSM modem disconnected) and then reconnects
        while self.ser.in_waiting == 0:
            time.sleep(0.1)

        try:
            # Should be "\r\n>>>"
            ready_for_data_entry = self.sio.read(5)
        except serial.SerialException:
            raise serial.SerialException("Failed to read from serial input buffer")

        print("DEBUG ready_for_data_entry is", "'" + ready_for_data_entry.replace('\r\n', '\\r\\n') + "'")

        if ready_for_data_entry != "\r\n>>>":
            raise ModemError(f"Modem returned {ready_for_data_entry} when \"\\r\\n>>>\" was expected")
        else:
            self.sio.write(data)
            self.sio.flush()

            while self.ser.in_waiting == 0:
                time.sleep(wait)
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
            rfsts = self.cmd_query("AT#RFSTS")

            # Check if modem is registered on a network
            if self.cmd_query("AT+COPS?").count(",") != 0:
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
        ws46_response = self.cmd_query("AT#WS46?")

        print("Checking GPS module status...")
        gpsp_response = self.cmd_query("AT$GPSP?")

        # Longer timeout due to network scan operation taking time
        print("Searching for available operators...")
        cops_response = self.cmd_query("AT+COPS=?", timeout=60)

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
