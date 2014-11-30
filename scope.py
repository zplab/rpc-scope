# The MIT License (MIT)
#
# Copyright (c) 2014 WUSTL ZPLAB
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Authors: Zach Pincus

from serial import SerialException

from .messaging import message_manager, message_device
from .device.dm6000b import stand, stage, objective_turret, illumination_axes
from .device.andor import camera
from .device.io_tool import io_tool
from .device import spectra_x
from .device import tl_lamp
from .device import acquisition_sequencer
from .device import autofocus
from .device import peltier
from .device import footpedal

from . import scope_configuration as config

def _print_exception(preamble, e):
    print(preamble + '\n\t' + str(e) + '\n')

class Namespace:
    pass

class Scope(message_device.AsyncDeviceNamespace):
    def __init__(self, property_server=None, verbose=False):
        super().__init__()

        if property_server:
            self.rebroadcast_properties = property_server.rebroadcast_properties

        try:
            manager = message_manager.LeicaMessageManager(config.Stand.SERIAL_PORT, config.Stand.SERIAL_BAUD, verbose=verbose)
            self.stand = stand.Stand(manager, property_server, property_prefix='scope.stand.')
            self.nosepiece = objective_turret.ObjectiveTurret(manager, property_server, property_prefix='scope.nosepiece.')
            self.stage = stage.Stage(manager, property_server, property_prefix='scope.stage.')
            self.il = illumination_axes.IL(manager, property_server, property_prefix='scope.il.')
            self.tl = illumination_axes.TL(manager, property_server, property_prefix='scope.tl.')
            has_scope = True
        except SerialException as e:
            has_scope = False
            _print_exception('Could not connect to microscope:', e)

        try:
            self.iotool = io_tool.IOTool()
            has_iotool = True
        except SerialException as e:
            has_iotool = False
            _print_exception('Could not connect to IOTool box:', e)

        if not has_scope and has_iotool:
            self.il = Namespace()
            self.tl = Namespace()

        if has_iotool:
            try:
                self.il.spectra_x = spectra_x.SpectraX(self.iotool, property_server, property_prefix='scope.il.spectra_x.')
                has_spectra_x = True
            except SerialException as e:
                has_spectra_x = False
                _print_exception('Could not connect to Spectra X:', e)
            self.tl.lamp = tl_lamp.TL_Lamp(self.iotool, property_server, property_prefix='scope.tl.lamp.')
            self.footpedal = footpedal.Footpedal(self.iotool)

        try:
            self.camera = camera.Camera(property_server, property_prefix='scope.camera.')
            has_camera = True
        except camera.lowlevel.AndorError as e:
            has_camera = False
            _print_exception('Could not connect to camera:', e)

        if has_camera and has_iotool and has_spectra_x:
            self.camera.acquisition_sequencer = acquisition_sequencer.AcquisitionSequencer(self.camera, self.iotool, self.il.spectra_x)

        if has_scope and has_camera:
            self.camera.autofocus = autofocus.Autofocus(self.camera, self.stage)

        try:
            self.peltier = peltier.Peltier(property_server, property_prefix='scope.peltier.')
        except SerialException as e:
            _print_exception('Could not connect to peltier controller:', e)
