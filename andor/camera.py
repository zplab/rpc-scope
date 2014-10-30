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
# Authors: Erik Hvatum, Zach Pincus

import weakref
from rpc_acquisition.andor import andor
from rpc_acquisition.enumerated_properties import DictProperty

class ReadOnly_AT_Enum(DictProperty):
    def __init__(self, feature):
        self._feature = feature
        super().__init__()

    def _get_hw_to_usr(self):
        str_count = andor.GetEnumCount(self._feature)
        return {idx : andor.GetEnumStringByIndex(self._feature, idx) for idx in range(str_count)}

    def _read(self):
        return andor.GetEnumIndex(self._feature)

class AT_Enum(ReadOnly_AT_Enum):
    def _write(self, value):
        andor.SetEnumIndex(self._feature, value)

class CameraCallbackContainer:
    @classmethod
    def register(cls, camera, property_name, feature):
        if hasattr(camera, property_name):
            # Property is enumerated
            getter = camera.__getattribute__(property_name).get_value
        else:
            # Property is a simple getter function
            getter = camera.__getattribute__('get_' + property_name)
        property_server = camera._property_server
        publish_update = property_server.add_property('scope.camera.' + property_name, getter())
        callback_container = cls(getter, publish_update)
        c_callback = andor.FeatureCallback(callback_container._callback)
        andor.RegisterFeatureCallback(feature, c_callback, 0)
        # NB: Retain this return value; it represents a ctypes wrapper to the bound method callback_container._callback.
        # The bound method descriptor stored by the wrapper will contain the only extant strong reference to callback_container
        # once this function returns.  Allowing the wrapper's reference count to drop to zero will cause its associated
        # CameraCallbackContainer (callback_container in this function's name space) to be deleted.
        return c_callback

    def __init__(self, getter, publish_update):
        self._pre_called = False
        self._getter = weakref.WeakMethod(getter)
        self._publish_update = publish_update
        self._c_callback = None

    def __del__(self):
        print('~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~DEL~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~')

    def _callback(self, camera_handle, feature, context):
        if self._pre_called:
            self._publish_update(self._getter()())
        else:
            # Ignore the call that occurs immediately upon registering callback
            self._pre_called = True
        return andor.AT_CALLBACK_SUCCESS

class Camera:
    '''This class provides an abstraction of the raw Andor API ctypes shim found in
    rpc_acquisition.andor.andor.

    Note that rpc_acquisition.andor.andor.initialize(..) should be called once before
    instantiating this class.'''

    def __init__(self, property_server=None):
        self._property_server = None
        self._c_callbacks = []
        if property_server is not None:
            self._attach_property_server(property_server)
        self.auxiliary_out_source = AT_Enum('AuxiliaryOutSource')
        self.binning = AT_Enum('AOIBinning')
        self.cycle_mode = AT_Enum('CycleMode')
        self.exposure_mode = AT_Enum('ElectronicShutteringMode')
        self.fan = AT_Enum('FanSpeed')
        self.io_selector = AT_Enum('IOSelector')
        self.sensor_selection = AT_Enum('SimplePreAmpGainControl')
        # NB: The only available TemperatureControl setting on the Zyla is 0.00, so there's not much reason to
        # expose this property
        # self.temperature_control = AT_Enum('TemperatureControl')
        self.temperature_status = ReadOnly_AT_Enum('TemperatureStatus')
        self.trigger_mode = AT_Enum('TriggerMode')

    def __del__(self):
        self._detach_property_server()

    def _attach_property_server(self, property_server):
        if self._property_server is not None:
            raise RuntimeError('Already attached to property_server.')
        self._property_server = property_server
        register_for = [
            ('exposure_time', 'ExposureTime'),
            ('auxiliary_out_source', 'AuxiliaryOutSource'),
            ('binning', 'AOIBinning'),
            ('cycle_mode', 'CycleMode')]
        for property_name, feature in register_for:
            self._c_callbacks.append((feature, CameraCallbackContainer.register(self, property_name, feature)))

    def _detach_property_server(self):
        if self._property_server is None:
            return
        for feature, c_callback in self._c_callbacks:
            andor.UnregisterFeatureCallback(feature, c_callback, 0)
            print('~~~~~~~~~~~~~~unregistered ' + feature)
        # TODO: Remove the associated unregistered properties from property_server?
        self._c_callbacks = []
        self._property_server = None

    def get_exposure_time(self):
        return andor.GetFloat('ExposureTime')

    def set_exposure_time(self, exposure_time):
        andor.SetFloat('ExposureTime', exposure_time)
