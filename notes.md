# Telit ME910G1 Linux USB Information
In `linux/drivers/usb/serial/option.c`, Telit ME910G1 has 2 mentions:
| Product Name | USB Vendor ID | USB Product ID | USB Interface Class |
| ------------ | ------------- | -------------- | ------------------- |
| ME910G1      | `0x1bc7`      | `0x110a`       | `0xff`              |
| ME910G1 (ECM)| `0x1bc7`      | `0x110b`       | `0xff`              |
| ------------ | ------------- | -------------- | ------------------- |
Interface class `0xff` is vendor-specific per [USB-IF](https://www.usb.org/defined-class-codes) specification.

Per Telit's Linux USB guide, product ID `0x110a` presents 3 reduced ACM (serial) interfaces handled `option` driver, as well as one rmnet adapter, handled by `qmi_wwan` driver. The rmnet adapter can only be used for controlling the device.
It may be necessary to disable high-level software for managing mobile broadband connection (ModemManager) as it may not expect this reduced capability of the rmnet adapter.

Use `lsusb -d 1bc7:` to check if the modem is connected.

If the modem is recognized, its reduced ACM interfaces should show up as `/dev/ttyUSB0` (or some other number), and there should be a network interface created (check `/sys/class/net`)
Find out the serial port parameters using `stty -F /dev/ttyUSB0`

[This](https://paldan.altervista.org/telit-me910g1-linux-support-composition-0x110a-available/?doing_wp_cron=1746978381.3163089752197265625000) seems to be a blog post on the ME910G1 patch to the kernel, written by the author.
