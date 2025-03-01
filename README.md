# pySMTrace

## Abstract

pySMTrace is a Python 3.5+ implementation of a simple Smart Meter tracing application based on
SML (Smart Message Language), OBIS (Object Identification System) and PCAPNG.
It receives SML telegrams from USB IR Write/Read interfaces, extracts OBIS informations from
SML_GetListRes messages contained in a telegram and can send EMails at configurable times with a
short plain text report of all last received data points or attached PCAPNG files.

## General Execution

* install Python 3.x.y
* install Python modules (e.g. via [pip](https://github.com/pypa/pip))
    * [apscheduler](https://github.com/agronholm/apscheduler)
    * [colorlog](https://github.com/borntyping/python-colorlog)
    * [croniter](https://github.com/corpusops/croniter)
    * [pyserial](https://github.com/pyserial/pyserial)
    * [pyyaml](https://github.com/yaml/pyyaml)
* clone the repository pySMTrace into any directory **\<PYSMTRACE\>**
* edit **pySMTrace.cfg** to your needs
* start data acquisition
    * open a command line and change dir into **\<PYSMTRACE\>**
    * type `python3 pySMTrace.py` and press `ENTER`
* enjoy pySMTrace
* close data acquisition
    * set focus on the command line window running the data acquisition and press `STRG+C`

## Use-case "DietPi" on Raspberry Pi Model B Rev 2

### preparations on a PC ###
* download [DietPi](https://dietpi.com/downloads/images/DietPi_RPi1-ARMv6-Bookworm.img.xz) ("Bookworm", for ARMv6)
* decompress downloaded file and write image to a SD memory card
    * adapt the file `dietpi.txt` on the SD memory card to at least:
    * `AUTO_SETUP_INSTALL_SOFTWARE_ID=17 130 200 \<what you need in addition\>`  \
(== Git, Python 3 pip, DietPi-Dashboard; see https://github.com/MichaIng/DietPi/wiki/DietPi-Software-list)
* connect the USB devices you want to use with the RasPi
    * identify via e.g. `lsusb` the ID (== \<idVendor\>:\<idProduct\>) of your device(s);  \
e.g. `Bus 001 Device 006: ID 0403:6001 Future Technology Devices International, Ltd FT232 Serial (UART) IC`
    * identify via e.g. `lsusb-v -d <ID> | grep iSerial` the individual serial number of your device(s)
* with root priveleges create a file `/usr/lib/udev/rules.d/<2-digit-number>_<name>.rules` (e.g. 99-usb-serial.rules) on the SD memory card with following content:
```
SUBSYSTEM=="tty", ATTRS{idVendor}=="<id_vendor_1st_device>", ATTRS{idProduct}=="<id_product_1st_device>", ATTRS{serial}=="<serial_1st_device>", MODE="0666", SYMLINK+="<symbolic_name_1st_device>"
SUBSYSTEM=="tty", ATTRS{idVendor}=="<id_vendor_2nd_device>", ATTRS{idProduct}=="<id_product_2nd_device>", ATTRS{serial}=="<serial_2nd_device>", MODE="0666", SYMLINK+="<symbolic_name_2nd_device>"
...
```
* with root priveleges create a file `/etc/systemd/system/pySMTrace.service` on the SD memory card with following content:
```
[Unit]
Description=pySMTrace

[Service]
Type=simple
ExecStart=python3 /home/dietpi/pySMTrace/pySMTrace.py'
ExecStop=
KillSignal=SIGINT
User=dietpi
WorkingDirectory=/home/dietpi/pySMTrace

[Install]
WantedBy=multi-user.target
```

* with user priveleges clone the Git repository of pySMTrace to /home/dietpi
* adapt the file pySMTrace.cfg to your needs

### RasPi ###
* insert the SD memory card
* connect the USB devices and ethernet
* plug in the power supply
* after 1st boot restart the system
* login as `dietpi`
* call `python3 -m pip install apscheduler colorlog croniter pyserial pyyaml`
* call `systemctl enable pySMTrace.service`
* call `systemctl start pySMTrace.service`
