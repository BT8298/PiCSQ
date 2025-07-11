#!/bin/sh
# Needs to be run as root
if [ $UID != 0 ]; then
	echo "Needs to be run as root"
fi

install -o root -g root -m 644 smartpark.service /etc/systemd/system
# This path is seemingly raspbian-specific; it differs for example in arch linux, where it is /lib/python3.11/site-packages
install -o root -g root -m 644 -d modules/ /lib/python3/dist-packages
install -o root -g root -m 755 -d scripts/ /usr/bin

# To uninstall, just remove each of the files from the directories they were moved to
