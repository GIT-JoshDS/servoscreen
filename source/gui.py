#!/usr/bin/python3

import traceback
import sys
import serial
import serial.tools.list_ports

from PyQt5 import QtGui
from PyQt5.QtCore import QObject, QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import QMainWindow, QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QMenu, QAction

import customwidgets
import ciedriver
import logging.config

logging.config.fileConfig('logging.ini', disable_existing_loggers=False)
logger = logging.getLogger(__name__)


class Worker(QObject):
    runtest = False
    finished = pyqtSignal()
    servoData = pyqtSignal()

    def close(self):
        pass

    def run(self, port, servo):
        """
        task
        :return:
        """
        while True:  # TODO: Add finish parameter.
            self.servo.readDataStream()

        #self.finished.emit()


class ServoMainWindow(QMainWindow):
    """
    Main servoMainWindow.
    """

    checkSerialPortTimerMsec = 5
    currentVentilationMode = "Ventilator not connected"
    IEChannels = ["Pressure Control", "Volume Control", "Pressure Reg. Volume Control"]

    def __init__(self, parent=None):
        """
        Initializer.
        """
        super().__init__(parent)
        logger.info('Creating ServoScreen main window.')

        # Set some main window properties.
        self.setWindowTitle('ServoScreen')
        self.setContentsMargins(0, 0, 0, 0)
        #self.setStyleSheet('border: 1px solid white;')  # Used for layout debugging purposes.

        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor('black'))
        self.setPalette(palette)

        self.centralWidget = QWidget(self)
        self.setCentralWidget(self.centralWidget)

        self.openPort = serial.Serial()

        logger.info('Creating window layout.')
        self._createLayout()
        logger.info('Creating window menu.')
        self._createMenu()

        # TODO: Add threading for serial communication.

        # TODO: Add timers for GUI data refresh.

        # TODO: Connect Numeric widgets to values.

    def _createLayout(self):
        """
        Set the main window layout.
        """
        generalLayout = QGridLayout()
        curvesLayout = QVBoxLayout()
        numericsLayout = QVBoxLayout()
        settingsLayout = QVBoxLayout()

        # Fill the layout.
        self.curvesWidgets = {}
        self.numericsWidgets = {}
        self.settingsWidgets = {310: customwidgets.Textbox()}

        settingsLayout.addWidget(self.settingsWidgets[310], 1)
        generalLayout.addLayout(settingsLayout, 0, 0, 1, 2)
        self.settingsWidgets[310].setText(self.currentVentilationMode)

        curves = [(101, 'cmH2O', 'yellow', 'bottom', -5, 35),
                  (100, 'l/min BTPS', 'green', 'middle', -1300, 500),
                  (114, 'l/min BTPS', 'teal', 'bottom', -50, 600)]

        for curve in curves:
            channel = curve[0]
            title = curve[1]
            colour = curve[2]
            axis = curve[3]
            minVal = curve[4]
            maxVal = curve[5]

            self.curvesWidgets[channel] = customwidgets.Waveform(title, colour, axis, minVal, maxVal)
            curvesLayout.addWidget(self.curvesWidgets[channel])

        generalLayout.addLayout(curvesLayout, 1, 0)
        generalLayout.setColumnStretch(0, 5)

        numerics = [(205, 'Ppeak', '(cmH2O)', 'yellow', 2),
                    (206, 'Pmean', '(cmH2O)', 'yellow', 1),
                    (208, 'PEEP', '(cmH2O)', 'yellow', 1),
                    (200, 'RR', '(br/min)', 'green', 2),
                    (209, 'O2', '(%)', 'green', 2),
                    (238, 'I:E', 'ratio', 'green', 1),
                    (248, 'MVe', '(l/min)', 'teal', 2),
                    (202, 'VTi', '(ml)', 'teal', 1),
                    (201, 'VTe', '(ml)', 'teal', 1)]

        for number in numerics:
            channel = number[0]
            name = number[1]
            unit = number[2]
            colour = number[3]
            size = number[4]

            if size > 1:
                self.numericsWidgets[channel] = customwidgets.LargeNumeric(name, unit, colour)
            else:
                self.numericsWidgets[channel] = customwidgets.SmallNumeric(name, unit, colour)

            numericsLayout.addWidget(self.numericsWidgets[channel], size)

        generalLayout.addLayout(numericsLayout, 1, 1)
        generalLayout.setColumnStretch(1, 1)

        self.centralWidget.setLayout(generalLayout)

    def _createMenu(self):
        menuBar = self.menuBar()
        fileMenu = QMenu('Menu', self)
        menuBar.addMenu(fileMenu)

        self.refreshSerialPortsAction = QAction('Refresh Serial Ports', self)
        self.refreshSerialPortsAction.triggered.connect(lambda: self._populateSerialPorts())
        fileMenu.addAction(self.refreshSerialPortsAction)

        self.connectMenu = fileMenu.addMenu('Connect to Servo Ventilator')
        self._populateSerialPorts()

        fileMenu.addSeparator()

        self.exitAction = QAction('Exit', self)
        self.exitAction.triggered.connect(lambda: self._disconnectSerialPort())
        fileMenu.addAction(self.exitAction)

    def _populateSerialPorts(self):
        """
        Clear and refill the 'Available Serial Ports' menu.
        :return:
        """
        self.connectMenu.clear()

        self.availableSerialPorts = serial.tools.list_ports.comports()

        connectActions = []
        for port in self.availableSerialPorts:
            action = QAction(port.name, self)
            action.triggered.connect(lambda *args, targetport=port: self._connectToSerialPort(targetport))
            connectActions.append(action)

        self.connectMenu.addActions(connectActions)

    def _connectToSerialPort(self, port):
        """
        Connect to specified serial port.
        :return:
        """
        logger.info('Connecting to serial port.')
        try:
            self.openPort = serial.Serial(
                port=port.name,
                baudrate=9600,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
                timeout=1
            )
        except serial.SerialException as err:
            logger.info('Could not connect to %s' % self.openPort.name)
            sys.stderr.write('\nCould not open serial port: {}\n'.format(err))
            sys.exit(1)
        finally:
            while self.openPort.in_waiting:
                self.openPort.read(1)

        logger.info('Connected to %s' % self.openPort.name)

        self._initialiseServo()

    def _disconnectSerialPort(self):
        """
        Close serial port and exit program.
        :return:
        """
        if self.openPort.is_open:
            self.timer.stop()
            self.servo.endDataStream()
            logger.info('Disconnected from %s' % self.openPort.name)
            self.openPort.close()
        logger.info('Closing ServoScreen main window.')
        sys.exit(0)

    def _initialiseServo(self):
        """
        This function initializes the ciedriver and configures the Servo Ventilator's CIE
        interface. It defines the data channels based on the lists defined earlier and sends
        them to the Servo.
        It also configures the GUI components which display the return data.
        """
        if self.openPort.is_open:
            self.servo = ciedriver.ServoCIE(self.openPort)

        if b'900PCI' not in self.servo.generalCall():
            logger.warning('Could not connect to Servo-i. Sending end data stream command and retrying.')
            self.servo.endDataStream()
            if b'900PCI' not in self.servo.generalCall():
                logger.warning('Could not connect to Servo-i.')
                self.settingsWidgets[310].setText('Failed to connect to Servo-i.')
                return

        logger.info('Connected to Servo-i. Setting protocol version.')
        self.servo.readCIType()
        maxProtocol = self.servo.getMaxProtocol()
        self.servo.setProtocol(maxProtocol)

        logger.info('Setting up data tables.')
        breathChannels = [200, 201, 202, 205, 206, 208, 209, 238, 244, 248]
        curveChannels = [100, 101, 114]
        settingChannels = [310]

        self.servo.defineAcquiredData('B', breathChannels)
        self.servo.defineAcquiredData('C', curveChannels)
        self.servo.defineAcquiredData('S', settingChannels)

        logger.info('Reading open channel configurations.')
        for key in self.servo.openChannels:
            for channel in self.servo.openChannels[key]:
                logger.debug('%s : %s' % (key, channel))
                self.servo.readChannelConfig(channel)
        logger.debug(self.servo.openChannels)

        logger.info('Starting Servo data stream.')
        self.currentVentilationMode = "Ventilator connected, waiting for Mode data"
        self.settingsWidgets[310].setText(self.currentVentilationMode)
        self.timer = QTimer()
        self.timer.timeout.connect(lambda: self.checkSerialPort())
        self.servo.startDataStream()
        self.timer.start(self.checkSerialPortTimerMsec)

        # TODO: Add multithreading to speed up serial responsiveness and keep GUI responsive.
        #self.thread = QThread()
        #self.worker = Worker()
        #self.worker.moveToThread(self.thread)

        #self.thread.started.connect(self.worker.run(self.openPort, self.servo))
        #self.worker.finished.connect(self.thread.quit)
        #self.worker.finished.connect(self.worker.deleteLater)
        #self.thread.finished.connect(self.thread.deleteLater)

        #self.thread.start()

    def checkSerialPort(self):
        """
        This function reads the deserialized data out of the ciedriver buffers and sends it to the
        correct GUI components.
        C = plot data
        S = setting data (only ventilation mode at present)
        B = breath data (numerical values)
        """
        if self.openPort.in_waiting:
            self.servo.readDataStream()
            for category in self.servo.channelData:
                if category == 'C':  # Leave last data in array.
                    for index, channel in enumerate(self.servo.channelData[category]):
                        while len(self.servo.channelData[category][channel]) > 1:
                            rawVal = self.servo.channelData[category][channel].pop(0)
                            gain = self.servo.openChannels[category][index][1]
                            offset = self.servo.openChannels[category][index][2]
                            value = round(rawVal * gain - offset, 3)
                            self.curvesWidgets[channel].updatePlot(value)

                if category == 'S':  # Safe to remove all data
                    for index, channel in enumerate(self.servo.channelData[category]):
                        while len(self.servo.channelData[category][channel]) > 0:
                            data = self.servo.channelData[category][channel].pop(0)
                            if data not in self.servo.ventilationMode:
                                self.settingsWidgets[channel].setText('Ventilator Mode Not Found')
                            else:
                                self.currentVentilationMode = self.servo.ventilationMode.get(data)
                                self.settingsWidgets[channel].setText(self.currentVentilationMode)
                                if self.currentVentilationMode not in ["Pressure Control",
                                                                       "Volume Control",
                                                                       "Pressure Reg. Volume Control"]:
                                    self.numericsWidgets[238].changeChannel('Ti:Ttot', 'ratio')
                                else:
                                    self.numericsWidgets[238].changeChannel('I:E', 'ratio')

                if category == 'B':  # Safe to remove all data
                    for index, channel in enumerate(self.servo.channelData[category]):
                        while len(self.servo.channelData[category][channel]) > 0:
                            rawVal = self.servo.channelData[category][channel].pop(0)
                            gain = self.servo.openChannels[category][index][1]
                            offset = self.servo.openChannels[category][index][2]
                            value = round(rawVal * gain - offset, 3)
                            if channel == 238 and self.currentVentilationMode not in ["Pressure Control",
                                                                                      "Volume Control",
                                                                                      "Pressure Reg. Volume Control"]:
                                self.numericsWidgets[channel].currentValue.setText("--")
                                self.numericsWidgets[channel].currentValue.show()
                            else:
                                self.numericsWidgets[channel].setValue(value)

                else: # catches empty data categories
                    #logger.debug('Empty data category: ' + category)
                    pass
