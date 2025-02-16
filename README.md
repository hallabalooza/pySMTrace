# pySMTrace

## Abstract

pySMTrace is a Python 3.5+ implementation of a simple Smart Meter tracing application based on
SML (Smart Message Language), OBIS (Object Identification System) and PCAPNG.
It receives SML telegrams from USB IR Write/Read interfaces, extracts OBIS informations from
SML_GetListRes messages contained in a telegram and can send EMails at configurable times with a
short plain text report of all last received data points or attached PCAPNG files.

## General Execution

* install Python 3.x.y
* install Python modules
  [colorama](https://github.com/tartley/colorama),
  [colorlog](https://github.com/borntyping/python-colorlog),
  [croniter](https://github.com/corpusops/croniter),
  [pyserial](https://github.com/pyserial/pyserial) and
  [pyyaml](https://github.com/yaml/pyyaml),
   e.g. via [pip](https://github.com/pypa/pip)
* clone the repository pySMTrace into any directory **\<PYSMTRACE\>**
* edit **pySMTrace.cfg** to your needs
* start data acquisition
  * open a command line and change dir into **\<PYSMTRACE\>**
  * type `python3 pySMTrace.py` and press `ENTER`
* enjoy pySMTrace
* close data acquisition
  * set focus on the command line window running the data acquisition and press `STRG+C`
