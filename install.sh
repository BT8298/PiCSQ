#!/bin/sh
# Needs to be run as root
if [ $UID != 0 ]; then
	echo "Needs to be run as root"
	exit 1
fi

install -o root -g root -m 644 smartpark.service /etc/systemd/system
# This path is seemingly raspbian-specific; it differs for example in arch linux, where it is /lib/python3.11/site-packages
install -o root -g root -m 644 modules/*.py /lib/python3/dist-packages/
install -o root -g root -m 755 scripts/smartpark_get_rx_stats.py /usr/bin/smartpark_get_rx_stats
install -o root -g root -m 755 scripts/smartpark_data_logger.py /usr/bin/smartpark_data_logger
# To uninstall, just remove each of the files from the directories they were moved to

systemctl stop ModemManager.service && systemctl disable ModemManager.service
systemctl enable smartpark.service
timedatectl set-ntp false
echo Daemon will autostart on next boot. To start now, run "systemctl start smartpark.service".
echo Don\'t forget to edit /usr/bin/smartpark_data_logger configuration values like server address near the top of the script!
