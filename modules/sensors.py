import lgpio
import time
import warnings

SHTC3_CMD_WAKEUP = b'\x35\x17'
SHTC3_CMD_SLEEP = b'\xb0\x98'
SHTC3_CMD_READ_TH = b'\x78\x66'
SHTC3_CMD_READ_HT = b'\x58\xe0'
SHTC3_CMD_LP_READ_TH = b'\x60\x9c'
SHTC3_CMD_LP_READ_HT = b'\x40\x1a'
SHTC3_CMD_CS_READ_TH = b'\x7c\xa2'
SHTC3_CMD_CS_READ_HT = b'\x5c\x24'
SHTC3_CMD_LPCS_READ_TH = b'\x64\x58'
SHTC3_CMD_LPCS_READ_HT = b'\x44\xde'
SHTC3_CMD_READ_ID_REGISTER = b'\xef\xc8'
SHTC3_CMD_SOFTWARE_RESET = b'\x80\x5d'

LPS22HB_REG_CTRL_1 = 0x10
LPS22HB_REG_CTRL_2 = 0x11
LPS22HB_REG_CTRL_3 = 0x12
LPS22HB_REG_STATUS = 0x27
LPS22HB_REG_PRESS_OUT_XL = 0x28
LPS22HB_REG_PRESS_OUT_L = 0x29
LPS22HB_REG_PRESS_OUT_H = 0x2A
LPS22HB_REG_TEMP_OUT_L = 0x2B
LPS22HB_REG_TEMP_OUT_H = 0x2C

class SHTC3:
    def __init__(self):
        # I2C address is hardcoded to 0x70 for this sensor
        self.handle = lgpio.i2c_open(1, 0x70)
        self.write_command(SHTC3_CMD_WAKEUP)
        self.write_command(SHTC3_CMD_SOFTWARE_RESET)
        self.write_command(SHTC3_CMD_SLEEP)

    def close(self):
        lgpio.i2c_close(self.handle)

    def _crc_check(self, data_bytes, checksum):
        """Check if the provided data matches a CRC checksum.
        Args:
            data_bytes (bytes): The bytes to perform the CRC check on.
            checksum (int): Unsigned big-endian CRC checksum to check against.

        """
        # Ideally this function would be using a CRC library to maintain readability, but at the time of writing this machine does not have internet access to install said library.
        crc = 0xff
        for byte in data_bytes:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = ((crc <<1) ^ 0x31) & 0xff
                else:
                    crc = (crc << 1) & 0xff
        return True if crc ^ 0x00 == checksum else False

    def write_command(self, word, delay=0.01):
        """Write a byte to an I2C address.

        Args:
            word (bytes): 2 bytes, with the first being the I2C register to write to, and the second is the value to write.
            delay (float): The time to wait before writing, in seconds.
        """
        time.sleep(delay)
        lgpio.i2c_write_byte_data(self.handle, word[0], word[1])

    def read_bytes(self, n_bytes, delay=0.01):
        """Read bytes from the I2C device
        
        Args:
            n_bytes (int): Number of bytes to read.
            delay (float): The time to wait before reading, in seconds.

        """
        time.sleep(delay)
        bytes_read, response = lgpio.i2c_read_device(self.handle, n_bytes)
        return response

    def get_temperature_humidity(self, do_crc=True):
        self.write_command(SHTC3_CMD_WAKEUP)
        self.write_command(SHTC3_CMD_READ_TH)
        # Expect 6 bytes
        th_response = self.read_bytes(6, delay=0.05)
        self.write_command(SHTC3_CMD_SLEEP)
        if do_crc:
            temperature_celsius = -45 + 175 * int.from_bytes(th_response[0:2]) / 2**16
            relative_humidity_percent = 100 * int.from_bytes(th_response[3:5]) / 2**16

            if not self._crc_check(th_response[0:2], th_response[2]):
                # Perhaps log this to syslog or something?
                warnings.warn("CRC check failed for temperature", RuntimeWarning)
                temperature_celsius = None
            if not self._crc_check(th_response[3:5], th_response[5]):
                warnings.warn("CRC check failed for relative humidity", RuntimeWarning)
                relative_humidity_percent = None
        else:
            temperature_celsius = -45 + 175 * int.from_bytes(th_response[0:2]) / 2**16
            relative_humidity_percent = 100 * int.from_bytes(th_response[3:5]) / 2**16

        return temperature_celsius, relative_humidity_percent

class LPS22HB:
    def __init__(self):
        # I2C address is hardcoded to 0x5c for this sensor
        self.handle = lgpio.i2c_open(1, 0x5c)

    def update_register(self, reg, bitmask):
        """

        Args:
            reg (int): The register to update.
            bitmask (int): A byte with which the old register value is OR'ed
                with. The bits that are 1 in the bitmask will be set to 1 in the
                register.
        """
        old_value = lgpio.i2c_read_byte_data(self.handle, reg)
        new_value = old_value | bitmask
        lgpio.i2c_write_byte_data(self.handle, reg, new_value)

    def get_pressure(self, attempts=10):
        # Set last bit of control register 2 to 1, to begin a oneshot acquisition
        self.update_register(LPS22HB_REG_CTRL_2, 0b00000001)
        # Check if new pressure data is available; indicated by bit 0
        _attempt = 1
        while (lgpio.i2c_read_byte_data(self.handle, LPS22HB_REG_STATUS ) & 0b00000001 == 0) and _attempt <= attempts:
            time.sleep(0.01)
            _attempt += 1
        if lgpio.i2c_read_byte_data(self.handle, LPS22HB_REG_STATUS) & 0b00000001 == 1:
            # Pressure is 3 bytes, stored as 2's complement, expressed as 4096 times the pressure in hPa
            pressure_lsb = lgpio.i2c_read_byte_data(self.handle, LPS22HB_REG_PRESS_OUT_XL)
            pressure_mid = lgpio.i2c_read_byte_data(self.handle, LPS22HB_REG_PRESS_OUT_L)
            pressure_msb = lgpio.i2c_read_byte_data(self.handle, LPS22HB_REG_PRESS_OUT_H)
            pressure_hpa = ((pressure_msb << 16) + (pressure_mid << 8) + pressure_lsb) / 4096
        else:
            warnings.warn("Could not retrieve pressure data in time", RuntimeWarning)
            pressure_hpa = None

        return pressure_hpa
