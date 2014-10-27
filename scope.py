import serial
import zmq

from rpc_acquisition import message_device
from rpc_acquisition import message_manager
from rpc_acquisition.dm6000b import illumination_axes
from rpc_acquisition.dm6000b import objective_turret
from rpc_acquisition.dm6000b import stand
from rpc_acquisition.dm6000b import stage
from rpc_acquisition.andor import (andor, camera)


SCOPE_PORT = '/dev/ttyScope'
SCOPE_BAUD = 115200
SCOPE_CAMERA = 'ZYLA-5.5-CL3'

class Scope(message_device.AsyncDeviceNamespace):
    def __init__(self, property_server, verbose=False):
        super().__init__()

        # need a timeout on the serial port so that the message manager thread can 
        # occasionally check its 'running' attribute to decide if it needs to quit.
        self._scope_serial = serial.Serial(SCOPE_PORT, baudrate=SCOPE_BAUD, timeout=5)
        self._message_manager = message_manager.LeicaMessageManager(self._scope_serial, verbose=verbose)

        self.il = illumination_axes.IL(self._message_manager)
        self.tl = illumination_axes.TL(self._message_manager)
        self.nosepiece = objective_turret.ObjectiveTurret(self._message_manager)
        self.stage = stage.Stage(self._message_manager)
        self.stand = stand.Stand(self._message_manager)

        # TODO: add camera object (non-async) and whatever else we have 
        # plugged into the scope. IOTool box, maybe.
        # The lumencor and LED controls will be stuffed into IL and TL.
        
        andor.initialize(SCOPE_CAMERA)
        self.camera = camera.Camera()
        self.camera._attach_property_server(property_server)
