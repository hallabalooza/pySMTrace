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

        def __init__(self, pCfg, pTrg, pIdf=None):
            self.__cfg = pCfg
            self.__trg = pTrg
            self.__idf = pIdf
            self.__dat = dict()
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
                        vSmtp.login(*self.__cfg["auth"])
                    vSmtp.send_message(vMssg, from_addr=None, to_addrs=None)

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

        def __init__(self, pCfg, pTrg, pIdf=None):
            self.__cfg = pCfg
            self.__trg = pTrg
            self.__idf = pIdf
            self.__dat = None
            self.__idb = None
            self.__nam = None
            self.__cnt = 0
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
                    vSmtp.login(*self.__cfg["auth"])
                vSmtp.send_message(vMssg, from_addr=None, to_addrs=None)

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
    def __init__(self, pCfg, pIdf=None):
        """
        @brief  Constructor.
        @param  pCfg  A Reporter configuration.
        @param  pIdf  A custom identifier.
        """
        self.__cfg = pCfg
        self.__idf = pIdf
        self.__trg = apscheduler.schedulers.background.BackgroundScheduler()
        self.__hdl = [eval(pyRPT.Hdl(vHdl)["class"]+"(vHdl, vTrg, vIdf)", {"SMTrace_Report": self, "vHdl":pyRPT.Hdl(vHdl), "vTrg": self.__trg, "vIdf": self.__idf}) for vHdl in self.__cfg["handlers"]]
        self.__trg.start()

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def __del__(self):
        """
        @brief  Destructor.
        """
        self.__trg.shutdown()

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def __pcapng_init(self):
        if (self.__pcp):
          vTimestamp = time.time_ns()
          self.__pcp.addSHB(pMajorVersion=1, pMinorVersion=0)
          self.__pcp.addIDB(pLinkType=1, pSnapLen=0, pOptions=[(pyPCAPNG.IDBOptionType.TSRESOL, [9]), (pyPCAPNG.IDBOptionType.NAME, bytes(pIdf, encoding="utf-8")), (pyPCAPNG.IDBOptionType.ENDOFOPT, [])])
          self.__pcp.addISB(pInterfaceId=int(0), pTimestamp=int(vTimestamp), pOptions=[(pyPCAPNG.ISBOptionType.STARTTIME, struct.pack("II", ((vTimestamp & 0xFFFFFFFF00000000) >> 32), (vTimestamp & 0x00000000FFFFFFFF))), (pyPCAPNG.ISBOptionType.ENDOFOPT, [])])

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def log(self, pData):
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
    def __init__(self, pIdf, pCfg):
        """
        @brief  Constructor.
        @param  pIdf  A HM meter identifier.
        @param  pCfg  A HM meter configuration.
        """
        self.__idf     = pIdf
        self.__cfg     = pCfg
        self.__rpt     = None
        self.__log     = pyLOG.Log(self.__cfg["logref"])
        self.__obs     = pyOBIS.OBIS()
        self.buffer    = bytearray()
        self.transport = None
        self.__log.log_callinfo()

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def connection_made(self, transport):
        """
        @brief  Stores transport.
        @param  transport  The instance used to write to serial port.
        """
        self.__log.log_callinfo()
        self.transport = transport

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def connection_lost(self, exc):
        """
        @brief  Forgets transport.
        @param  exc  Exception if connection was terminated by error else None.
        """
        self.__log.log_callinfo()
        self.transport = None
        super(SMTrace_SMLPacket, self).connection_lost(exc)

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def data_received(self, data):
        """
        @brief  Buffer receives data and searchs for SML_Telegram terminators, when found, call handle_packet().
        @param  data  Bytes received via serial port.
        """
        self.__log.log_callinfo()
        self.buffer.extend(data)
        packets = [packet for packet in re.finditer(bytes("(?<!\x1b\x1b\x1b\x1b)\x1b\x1b\x1b\x1b\x01\x01\x01\x01.*?(?<!\x1b\x1b\x1b\x1b)\x1b\x1b\x1b\x1b\x1a(\x00|\x01|\x02|\x03)..".encode("ascii")), self.buffer, re.DOTALL)]
        if ( packets != [] ):
            for packet in packets:
                self.handle_packet(self.buffer[packet.start():packet.end()])
            del self.buffer[:packets[-1].end()]

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def prepare(self):
        """
        @brief  Prepare the processing of completely received packest. This is firstly called in a threads run method.
        """
        self.__log.log_callinfo()
        self.__rpt = SMTrace_Report(pyRPT.Rpt(self.__cfg["rptref"]), self.__idf + " / " + self.__cfg["note"])

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def disperse(self):
        """
        @brief  Disperse the processing of completely received packest. This is lastly called in a threads run method.
        """
        self.__log.log_callinfo()
        del(self.__rpt)

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def handle_packet(self, packet):
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

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    def __call__(self):
        """
        @brief  Call operator.
        """
        self.__log.log_callinfo()
        return self


########################################################################################################################


class SMTrace_Thread(serial.threaded.ReaderThread):
  """
  @brief  Customized version of serial.threaded.ReaderThread, that calls specific protocol_factory methods at the
          beginning and at the end of the receive thread.
  """

  def __init__(self, serial_instance, protocol_factory):
    """
    @brief  Constructor.
    @param  serial_instance   Serial port instance (opened) to be used.
    @param  protocol_factory  A callable that returns a Protocol instance.
    """
    super(SMTrace_Thread, self).__init__(serial_instance, protocol_factory)
    self.__stop = threading.Event()

  def close(self):
    """
    @brief  Close the serial port and exit reader thread.
    """
    if (None != self.protocol):
      self.__stop.set()
    super(SMTrace_Thread, self).close()

  def run(self):
    """
    @brief  The actual reader loop driven by the thread.
    """
    if (None == self.protocol):
      if (not hasattr(self.serial, 'cancel_read')):
        self.serial.timeout = 1
      self.protocol = self.protocol_factory()
      self.protocol.prepare()
      try:
        self.protocol.connection_made(self)
      except Exception as e:
        self.alive = False
        self.protocol.connection_lost(e)
        self._connection_made.set()
        return
      error = None
      self._connection_made.set()
      while (self.alive and self.serial.is_open):
        try:
          # read all that is there or wait for one byte (blocking)
          data = self.serial.read(self.serial.in_waiting or 1)
        except serial.SerialException as e:
          # probably some I/O problem such as disconnected USB serial
          # adapters -> exit
          error = e
          break
        else:
          if (data):
            try:
              self.protocol.data_received(data)
            except Exception as e:
              error = e
              break
        if (True == self.__stop.is_set()):
          self.protocol.disperse()
          break
      self.alive = False
      self.protocol.connection_lost(error)
      self.protocol = None


########################################################################################################################


class SMTrace:
  """
  @brief  SMTrace data tracing main class.
  """

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __init__(self, pCfg):
    """
    @brief  Constructor.
    @param  pCfg  SMTrace configuration.
    """
    self.__cfg   = pCfg
    self.__log   = pyLOG.Log(self.__cfg["general"]["logref"])
    self.__thd   = {}

    vMapBytesize = {5:serial.FIVEBITS, 6:serial.SIXBITS, 7:serial.SEVENBITS, 8:serial.EIGHTBITS}
    vMapStopbits = {1:serial.STOPBITS_ONE, 15:serial.STOPBITS_ONE_POINT_FIVE, 2:serial.STOPBITS_TWO}
    vMapParity   = {"none":serial.PARITY_NONE, "even":serial.PARITY_EVEN, "odd":serial.PARITY_ODD, "mark":serial.PARITY_MARK, "space":serial.PARITY_SPACE}

    self.__log.log_callinfo()

    for idf_meter, cfg_meter in self.__cfg["meters"].items():
      self.__log.log(pyLOG.LogLvl.INFO, "configuring meter '{}' started".format(idf_meter))
      try:
        self.__thd[idf_meter] = SMTrace_Thread(serial.Serial(port     = cfg_meter["serial"][0],
                                                             baudrate = cfg_meter["serial"][1],
                                                             bytesize = vMapBytesize[cfg_meter["serial"][2]],
                                                             stopbits = vMapStopbits[cfg_meter["serial"][3]],
                                                             parity   = vMapParity  [cfg_meter["serial"][4]],
                                                             timeout  = 0
                                                            ),
                                                            SMTrace_SMLPacket(idf_meter, cfg_meter)
                                              )
        self.__thd[idf_meter].start()
        for tk,tv in self.__thd.items():
          self.__log.log(pyLOG.LogLvl.INFO, "  receive thread '{}' started".format(tv))
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
    time.sleep(0.1)
  os._exit(1)


########################################################################################################################
########################################################################################################################
########################################################################################################################


if (__name__ == '__main__'):

    vCfg = None

    with open("pySMTrace.cfg", "r") as fhdl:
        vCfg = yaml.load(fhdl.read(), Loader=yaml.SafeLoader)

    signal.signal(signal.SIGINT, signal_handler)

    pyLOG.LogInit(vCfg["general"]["logger"])
    pyRPT.RptInit(vCfg["general"]["reporter"])

    vSMTrace = SMTrace(vCfg)

    while (True):
        time.sleep(30)
