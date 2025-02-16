#! /bin/bash

#--------------------------------------------------------------------

PYT_EXE=python3
PYT_OPT=
SCR_EXE=pySMTrace.py
SCR_OPT=
PWD_EXE=$(pwd)

#--------------------------------------------------------------------

start() {
  ${PYT_EXE} ${PYT_OPT} ${SCR_EXE} ${SCR_OPT}
}

stop() {
  kill -INT $(pgrep -f ${SCR_EXE})
}

#--------------------------------------------------------------------

cd $(dirname ${BASH_SOURCE[0]})

case $1 in
  start|stop) "$1" ;;
esac

cd ${PWD_EXE}
