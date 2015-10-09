# The MIT License (MIT)
#
# Copyright (c) 2014-2015 WUSTL ZPLAB
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
from .device.leica import stand, stage, objective_turret, illumination_axes
from .device.andor import camera
from .device.io_tool import io_tool
from .device import spectra_x
from .device import tl_lamp
from .device import acquisition_sequencer
from .device import autofocus
from .device import peltier
from .device import footpedal

from .config import scope_configuration

from .util import logging
logger = logging.get_logger(__name__)


class Namespace:
    pass

class Scope(message_device.AsyncDeviceNamespace):
    def __init__(self, property_server=None):
        super().__init__()

        self.get_configuration = scope_configuration.get_config
        config = self.get_configuration()

        if property_server:
            self.rebroadcast_properties = property_server.rebroadcast_properties

        try:
            logger.info('Looking for microscope.')
            manager = message_manager.LeicaMessageManager(config.Stand.SERIAL_PORT, config.Stand.SERIAL_BAUD)
            self.stand = stand.Stand(manager, property_server, property_prefix='scope.stand.')
            self.nosepiece = objective_turret.ObjectiveTurret(manager, property_server, property_prefix='scope.nosepiece.')
            self.stage = stage.Stage(manager, property_server, property_prefix='scope.stage.')
            self.il = illumination_axes.IL(manager, property_server, property_prefix='scope.il.')
            self.tl = illumination_axes.TL(manager, property_server, property_prefix='scope.tl.')
            self._shutter_openedness_watcher = illumination_axes.ShutterOpenednessWatcher(manager, property_server, property_prefix='scope.')
            has_scope = True
        except SerialException:
            has_scope = False
            logger.log_exception('Could not connect to microscope:')

        try:
            logger.info('Looking for IOTool.')
            self.iotool = io_tool.IOTool()
            has_iotool = True
        except SerialException:
            has_iotool = False
            logger.log_exception('Could not connect to IOTool:')

        if (not has_scope) and has_iotool:
            self.il = Namespace()
            self.tl = Namespace()

        if has_iotool:
            try:
                logger.info('Looking for Spectra X.')
                self.il.spectra_x = spectra_x.SpectraX(self.iotool, property_server, property_prefix='scope.il.spectra_x.')
                has_spectra_x = True
            except SerialException:
                has_spectra_x = False
                logger.log_exception('Could not connect to Spectra X:')
            self.tl.lamp = tl_lamp.TL_Lamp(self.iotool, property_server, property_prefix='scope.tl.lamp.')
            self.footpedal = footpedal.Footpedal(self.iotool)

        try:
            logger.info('Looking for camera.')
            self.camera = camera.Camera(property_server, property_prefix='scope.camera.')
            has_camera = True
        except camera.lowlevel.AndorError:
            has_camera = False
            logger.log_exception('Could not connect to camera:')

        if has_camera and has_iotool and has_spectra_x:
            self.camera.acquisition_sequencer = acquisition_sequencer.AcquisitionSequencer(self)

        if has_scope and has_camera:
            self.camera.autofocus = autofocus.Autofocus(self.camera, self.stage)

        try:
            logger.info('Looking for peltier controller.')
            self.peltier = peltier.Peltier(property_server, property_prefix='scope.peltier.')
        except SerialException:
            logger.log_exception('Could not connect to peltier controller:')

