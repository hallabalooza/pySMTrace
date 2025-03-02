# pySMTrace
# Copyright (C) 2025  Hallabalooza
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with this program. If not, see
# <http://www.gnu.org/licenses/>.


########################################################################################################################


import apscheduler.schedulers.background
import apscheduler.triggers.cron
import croniter
import datetime
import email
import email.mime.application
import email.mime.multipart
import email.mime.text
import inspect
import os
import os.path
import pyLOG
import pyOBIS
import pyPCAPNG
import pySML
import re
import serial, serial.threaded
import signal
import smtplib
import struct
import threading
import traceback
import time
import yaml

from collections import OrderedDict


########################################################################################################################


class pyRPT(object):

    __cfg = None

    @staticmethod
    def RptInit(pCfg):
        pyRPT.__cfg = pCfg

    @staticmethod
    def Rpt(pName):
        return pyRPT.__cfg["reporters"][pName]

    @staticmethod
    def Hdl(pName):
        return pyRPT.__cfg["handlers"][pName]

    @staticmethod
    def dump():
        print(pyRPT.__cfg)


########################################################################################################################


class SMTrace_Exception(Exception):
    """
    @brief  HM data tracing exception class.
    """

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def __init__(self, pMssg=None):
        """
        @brief  Constructor.
        @param  Mssg  The Exception message.
        """
        self._modl = inspect.stack()[1][0].f_locals["self"].__class__.__module__
        self._clss = inspect.stack()[1][0].f_locals["self"].__class__.__name__
        self._mthd = inspect.stack()[1][0].f_code.co_name
        self._mssg = None
        if   (pMssg == None): self._mssg = "{}.{}.{}".format(self._modl, self._clss, self._mthd)
        else                : self._mssg = "{}.{}.{}: {}".format(self._modl, self._clss, self._mthd, {True:"---", False:pMssg}[pMssg==None])

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def __str__(self):
        """
        @brief  Prints a nicely string representation.
        """
        return repr(self._mssg)


########################################################################################################################


class SMTrace_Report(object):
    """
    @brief  HM reporting class.
    """

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    class EMailTxt(object):

        def __init__(self, pCfg:dict, pTrg:apscheduler.schedulers.background.BackgroundScheduler, pLog:pyLOG.Log=None, pIdf=None):
            self.__cfg = pCfg
            self.__dat = dict()
            self.__idf = pIdf
            self.__log = pLog
            self.__trg = pTrg
            for v_cron in self.__cfg["cron"]:
                self.__trg.add_job(self, trigger=apscheduler.triggers.cron.CronTrigger().from_crontab(v_cron))

        def __call__(self):
            vSubj = None
            vText = None
            vSmtp = None
            vMssg = email.message.EmailMessage()
            if (self.__dat):
                vText = ""
                vMaxLenKey  = max([0] + [len(x) for x in self.__dat.keys()])
                vMaxLenUnit = max([2] + [len(v["unit"]) for k,v in self.__dat.items() if v["unit"] is not None])
                for k,v in sorted(self.__dat.items(), key=lambda x: [x[1]["tstmp"], x[0]]):
                    vKey  = k
                    vUnit = v["unit"]
                    if (isinstance(vKey,  bytes)): vKey  = vKey.decode("utf-8")
                    if (isinstance(vUnit, bytes)): vUnit = vUnit.decode("utf-8")
                    vText += "{fTstmp} | {fKey:<{fKeyWidth}} | {fUnit:<{fUnitWidth}} | {fValu}\n".format(fTstmp=v["tstmp"].isoformat(), fKey=vKey, fKeyWidth=vMaxLenKey, fUnit=vUnit if (vUnit is not None) else "--", fUnitWidth=vMaxLenUnit, fValu=v["valu"] if (v["valu"] is not None) else "--")
                vMssg.add_header("From", self.__cfg["from"])
                vMssg.add_header("To",   self.__cfg["to"  ])
                if (self.__cfg["cc"]       is not None): vMssg.add_header("Cc",      self.__cfg["cc"].replace(";", ",").strip(","))
                if (self.__cfg["subjprfx"] is not None): vSubj = self.__cfg["subjprfx"]
                if (self.__idf             is not None): vSubj = self.__idf if (vSubj is None) else vSubj + self.__idf
                if (vSubj                  is not None): vMssg.add_header("Subject", vSubj)
                vMssg.set_content(vText)
                with smtplib.SMTP(self.__cfg["srvr"], self.__cfg["port"]) as vSmtp:
                    if (    (self.__cfg["type"] == "STARTTLS"    )
                        and (isinstance(self.__cfg["auth"], list))
                        and (len(self.__cfg["auth"]) == 2        )
                       ):
                        vSmtp.starttls()
                        try:
                            vSmtp.login(*self.__cfg["auth"])
                        except:
                            if (self.__log is not None): self.__log.log(pyLOG.LogLvl.ERROR, "Could not login into '{fSrvr}:{fPort}'".format(fSrvr=self.__cfg["srvr"], fPort=self.__cfg["port"]))
                    try:
                        vSmtp.send_message(vMssg, from_addr=None, to_addrs=None)
                        if (self.__log is not None): self.__log.log(pyLOG.LogLvl.INFO, "Email successfully sent to '{fTo}'".format(fTo=self.__cfg["to"]))
                    except:
                        if (self.__log is not None): self.__log.log(pyLOG.LogLvl.ERROR, "Could not send email to '{fTo}'".format(fTo=self.__cfg["to"]))

        def log(self, pTimestamp:int, pData:dict):
            """
            @brief  tbd
            @param  pTimestamp  Integer number of nanoseconds since the epoch.
            @param  pData       tbd
            """
            if (not isinstance(pTimestamp, int) ): raise SMTrace_Exception("Parameter 'pTimestamp' is not of type 'int'.")
            if (not isinstance(pData,      dict)): raise SMTrace_Exception("Parameter 'pData' is not of type 'dict'.")
            for k,v in pData.items():
                if (not isinstance(v, dict)                   ): raise SMTrace_Exception("Value for key '{}' of parameter 'pData' is not of type 'dict'.".format(k))
                if (sorted(list(v.keys())) != ["unit", "valu"]): raise SMTrace_Exception("Value for key '{}' of parameter 'pData' does not include exactly the keys 'valu' and 'unit'.".format(k))
            for k,v in pData.items():
                if (k in self.__dat): self.__dat[k].update(dict(tstmp=datetime.datetime.utcfromtimestamp(pTimestamp/1E9), **v))
                else                : self.__dat[k] = dict(tstmp=datetime.datetime.utcfromtimestamp(pTimestamp/1E9), **v)

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    class EMailSml(object):

        def __init__(self, pCfg:dict, pTrg:apscheduler.schedulers.background.BackgroundScheduler, pLog:pyLOG.Log=None, pIdf=None):
            self.__cfg = pCfg
            self.__cnt = 0
            self.__dat = None
            self.__idb = None
            self.__idf = pIdf
            self.__log = pLog
            self.__nam = None
            self.__trg = pTrg
            for v_cron in self.__cfg["cron"]:
                self.__trg.add_job(self, trigger=apscheduler.triggers.cron.CronTrigger().from_crontab(v_cron))
            self.__open(time.time_ns())

        def __del__(self):
            self.__close()

        def __call__(self):
            vSubj = None
            vSmtp = None
            vPart = None
            vMssg = email.mime.multipart.MIMEMultipart()
            vMssg.add_header("From", self.__cfg["from"])
            vMssg.add_header("To",   self.__cfg["to"  ])
            if (self.__cfg["cc"]       is not None): vMssg.add_header("Cc",      self.__cfg["cc"].replace(";", ",").strip(","))
            if (self.__cfg["subjprfx"] is not None): vSubj = self.__cfg["subjprfx"]
            if (self.__idf             is not None): vSubj = self.__idf if (vSubj is None) else vSubj + self.__idf
            if (vSubj                  is not None): vMssg.add_header("Subject", vSubj)
            vMssg.attach(email.mime.text.MIMEText("---"))
            with open(self.__nam, "rb") as vFhdl:
                vPart = email.mime.application.MIMEApplication(vFhdl.read(), Name=os.path.basename(self.__nam))
                vPart.add_header('Content-Disposition', 'attachment; filename={}'.format(os.path.basename(self.__nam)))
                vMssg.attach(vPart)
            with smtplib.SMTP(self.__cfg["srvr"], self.__cfg["port"]) as vSmtp:
                if (    (self.__cfg["type"] == "STARTTLS"    )
                    and (isinstance(self.__cfg["auth"], list))
                    and (len(self.__cfg["auth"]) == 2        )
                   ):
                    vSmtp.starttls()
                    try:
                        vSmtp.login(*self.__cfg["auth"])
                    except:
                        if (self.__log is not None): self.__log.log(pyLOG.LogLvl.ERROR, "Could not login into '{fSrvr}:{fPort}'".format(fSrvr=self.__cfg["srvr"], fPort=self.__cfg["port"]))
                try:
                    vSmtp.send_message(vMssg, from_addr=None, to_addrs=None)
                    if (self.__log is not None): self.__log.log(pyLOG.LogLvl.INFO, "Email successfully sent to '{fTo}'".format(fTo=self.__cfg["to"]))
                except:
                    if (self.__log is not None): self.__log.log(pyLOG.LogLvl.ERROR, "Could not send email to '{fTo}'".format(fTo=self.__cfg["to"]))

        def __open(self, pTimestamp:int):
            self.__cnt = 0
            self.__nam = os.path.join(self.__cfg["location"], datetime.datetime.utcnow().strftime(re.sub("%N", re.sub("\W+", "_", self.__idf), self.__cfg["naming"])))
            self.__dat = pyPCAPNG.PCAPNGWriter(self.__nam, pMode="w", pAF=self.__cfg["samplerate"])
            self.__dat.addSHB(pMajorVersion=1, pMinorVersion=0)
            self.__idb = self.__dat.addIDB(pLinkType=1, pSnapLen=0, pOptions=[(pyPCAPNG.IDBOptionType.TSRESOL, [9]), (pyPCAPNG.IDBOptionType.NAME, bytes(self.__idf, encoding="utf-8")), (pyPCAPNG.IDBOptionType.ENDOFOPT, [])])
            self.__dat.addISB(pInterfaceId=int(0), pTimestamp=pTimestamp, pOptions=[(pyPCAPNG.ISBOptionType.STARTTIME, struct.pack("II", ((pTimestamp & 0xFFFFFFFF00000000) >> 32), (pTimestamp & 0x00000000FFFFFFFF))), (pyPCAPNG.ISBOptionType.ENDOFOPT, [])])

        def __close(self):
            self.__dat.flush()
            del(self.__dat)
            self.__dat = None

        def log(self, pTimestamp:int, pData:pySML.SML_Telegram):
            """
            @brief  tbd
            @param  pTimestamp  Integer number of nanoseconds since the epoch.
            @param  pData       tbd
            """
            if (not isinstance(pTimestamp, int)               ): raise SMTrace_Exception("Parameter 'pTimestamp' is not of type 'int'.")
            if (not isinstance(pData,      pySML.SML_Telegram)): raise SMTrace_Exception("Parameter 'pData' is not of type 'pySML.SML_Telegram'.")
            if (self.__cnt == self.__cfg["samplerate"]):
                self.__cnt = 0
                self.__dat.addEPB(pInterfaceId=self.__dat.getInterfaceId(self.__idb), pPacketData=pyPCAPNG.IPv4(pData=pData.data, pPortSrc=7259).eth, pTimestamp=pTimestamp) # pPortSrc=7259 ... WireShark SML protocol
            self.__cnt += 1

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def __init__(self, pCfg:dict, pLog:pyLOG.Log=None, pIdf=None):
        """
        @brief  Constructor.
        @param  pCfg  A Reporter configuration.
        @param  pIdf  A custom identifier.
        """
        self.__cfg = pCfg
        self.__idf = pIdf
        self.__trg = apscheduler.schedulers.background.BackgroundScheduler()
        self.__log = pLog
        self.__hdl = [eval(pyRPT.Hdl(vHdl)["class"]+"(vHdl, vTrg, vLog, vIdf)", {"SMTrace_Report": self, "vHdl":pyRPT.Hdl(vHdl), "vTrg": self.__trg, "vLog":self.__log, "vIdf": self.__idf}) for vHdl in self.__cfg["handlers"]]
        self.__trg.start()

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def __del__(self):
        """
        @brief  Destructor.
        """
        self.__trg.shutdown()

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def log(self, pData:dict):
        """
        @brief  Process a completely received packet. This is repetitive called in a threads run method.
        @param  pData  A SML_Telegram.
        """
        vTstmp = time.time_ns()
        for vHdl in self.__hdl:
            if   (isinstance(vHdl, self.EMailTxt) and isinstance(pData, dict              )): vHdl.log(vTstmp, pData)
            elif (isinstance(vHdl, self.EMailSml) and isinstance(pData, pySML.SML_Telegram)): vHdl.log(vTstmp, pData)


########################################################################################################################


class SMTrace_SMLPacket(serial.threaded.Protocol):
    """
    @brief  HM data tracing SML packet serial receive class.
    """

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def __init__(self, pIdf:str, pCfg:dict):
        """
        @brief  Constructor.
        @param  pIdf  A HM meter identifier.
        @param  pCfg  A HM meter configuration.
        """
        self.__buffer    = bytearray()
        self.__log       = pyLOG.Log(pCfg["logref"])
        self.__obs       = pyOBIS.OBIS()
        self.__rpt       = SMTrace_Report(pyRPT.Rpt(pCfg["rptref"]), self.__log, pIdf + " / " + pCfg["note"])
        self.__transport = None
        self.__log.log_callinfo()

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def __del__(self):
        """
        @brief  Destructor
        """
        self.__log.log_callinfo()
        del(self.__rpt)

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def __call__(self):
        """
        @brief  Call operator.
        """
        self.__log.log_callinfo()
        return self

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def connection_made(self, transport):
        """
        @brief  Stores transport.
        @param  transport  The instance used to write to serial port.
        """
        self.__log.log_callinfo()
        self.__transport = transport

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def connection_lost(self, exc):
        """
        @brief  Forgets transport.
        @param  exc  Exception if connection was terminated by error else None.
        """
        self.__log.log_callinfo()
        self.__transport = None
        super(SMTrace_SMLPacket, self).connection_lost(exc)

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def data_received(self, data:bytes):
        """
        @brief  Buffer receives data and searchs for SML_Telegram terminators, when found, call handle_packet().
        @param  data  Bytes received via serial port.
        """
        self.__log.log_callinfo()
        self.__buffer.extend(data)
        packets = [packet for packet in re.finditer(bytes("(?<!\x1b\x1b\x1b\x1b)\x1b\x1b\x1b\x1b\x01\x01\x01\x01.*?(?<!\x1b\x1b\x1b\x1b)\x1b\x1b\x1b\x1b\x1a(\x00|\x01|\x02|\x03)..".encode("ascii")), self.__buffer, re.DOTALL)]
        if ( packets != [] ):
            for packet in packets:
                self.__handle_packet(self.__buffer[packet.start():packet.end()])
            del self.__buffer[:packets[-1].end()]

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def __handle_packet(self, packet:bytes):
        """
        @brief  Process a completely received packet. This is repetitive called in a threads run method.
        @param  packet  A SML_Telegram.
        """
        self.__log.log_callinfo()
        try:
            vTelegram      = pySML.SML_Telegram()
            vTelegram.data = packet
            vData          = dict()
            self.__rpt.log(vTelegram)
            for vMssg in vTelegram.msg:
                if (isinstance(vMssg.MessageBody.Element, pySML.SML_GetListRes)):
                    for i,val in enumerate(vMssg.MessageBody.Element.ValList.valu):
                        vKey    = self.__obs.getDescr(int(val.ObjName.valu.hex(), 16))["descr"]
                        vValue  = val.Value.Element.valu
                        vScaler = val.Scaler.valu
                        vUnit   = None
                        if (val.Unit.valu is not None):
                            vUnit = self.__obs.getUnit(val.Unit.valu)["native"]
                        if (    (vValue is not None           )
                            and (isinstance(vValue, bytearray))
                           ):
                            try   : vValue = "\"" + vValue.decode("utf-8") + "\""
                            except: vValue = " ".join(["{:02X}".format(b) for b in vValue])
                        elif (vScaler is not None):
                            if   (0 > vScaler): vValue = vValue / (10*(-vScaler))
                            else              : vValue = vValue * (10**vScaler)
                        else:
                            pass
                        vData[vKey] = dict(valu=vValue, unit=vUnit)
            if (vData):
                self.__rpt.log(vData)
        except Exception as e:
            self.__log.log(pyLOG.LogLvl.ERROR, "\n{}\n{}".format(e, packet))


########################################################################################################################


class SMTrace:
  """
  @brief  SMTrace data tracing main class.
  """

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __init__(self, pCfg:dict):
    """
    @brief  Constructor.
    @param  pCfg  SMTrace configuration.
    """
    self.__cfg   = pCfg
    self.__log   = pyLOG.Log(self.__cfg["general"]["logref"])
    self.__thd   = {}

    self.__log.log_callinfo()

    vMapBytesize = {5:serial.FIVEBITS, 6:serial.SIXBITS, 7:serial.SEVENBITS, 8:serial.EIGHTBITS}
    vMapStopbits = {1:serial.STOPBITS_ONE, 15:serial.STOPBITS_ONE_POINT_FIVE, 2:serial.STOPBITS_TWO}
    vMapParity   = {"none":serial.PARITY_NONE, "even":serial.PARITY_EVEN, "odd":serial.PARITY_ODD, "mark":serial.PARITY_MARK, "space":serial.PARITY_SPACE}

    for idf_meter, cfg_meter in self.__cfg["meters"].items():
      self.__log.log(pyLOG.LogLvl.INFO, "configuring meter '{}' started".format(idf_meter))
      try:
        self.__thd[idf_meter] = serial.threaded.ReaderThread(serial.Serial(port     = cfg_meter["serial"][0],
                                                                           baudrate = cfg_meter["serial"][1],
                                                                           bytesize = vMapBytesize[cfg_meter["serial"][2]],
                                                                           stopbits = vMapStopbits[cfg_meter["serial"][3]],
                                                                           parity   = vMapParity  [cfg_meter["serial"][4]],
                                                                           timeout  = None
                                                                          ),
                                                             SMTrace_SMLPacket(idf_meter, cfg_meter)
                                                            )
        self.__thd[idf_meter].start()
        self.__log.log(pyLOG.LogLvl.INFO, "  receive thread '{}' started".format(self.__thd[idf_meter]))
        self.__log.log(pyLOG.LogLvl.INFO, "configuring meter '{}' done".format(idf_meter))
      except:
        self.__log.log(pyLOG.LogLvl.ERROR, "configuring meter '{}' failed".format(idf_meter))
        self.__log.log(pyLOG.LogLvl.ERROR, "{}".format(traceback.format_exc()))

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def isalive(self):
    """
    @brief  Returns whether a SMTrace_Thread is running or not.
    """
    for tk, tv in self.__thd.items():
      if (True == tv.alive): return True
    return False

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def stop(self):
    """
    @brief  Trigger exiting threads.
    """
    self.__log.log_callinfo()
    for tk, tv in self.__thd.items():
      self.__log.log(pyLOG.LogLvl.INFO, "deconfiguring meter '{}' started".format(tk))
      tv.close()
      self.__log.log(pyLOG.LogLvl.INFO, "  receive thread '{}' stopped".format(tv))
      self.__log.log(pyLOG.LogLvl.INFO, "deconfiguring meter '{}' done".format(tk))


########################################################################################################################


def signal_handler(signal, frame):
  """
  @brief  Application interrupt handler function.
  """
  global vSMTrace
  vSMTrace.stop()
  while (True == vSMTrace.isalive()):
    time.sleep(2.5)
  os._exit(1)


########################################################################################################################
########################################################################################################################
########################################################################################################################


if (__name__ == '__main__'):

    vCfg = None

    with open("pySMTrace.cfg", "r") as fhdl:
        vCfg = yaml.load(fhdl.read(), Loader=yaml.SafeLoader)

    signal.signal(signal.SIGINT,  signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    pyLOG.LogInit(vCfg["general"]["logger"])
    pyRPT.RptInit(vCfg["general"]["reporter"])

    vSMTrace = SMTrace(vCfg)

    while (True):
        time.sleep(30.0)
