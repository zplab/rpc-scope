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

class Camera:
    '''This class provides an abstraction of the raw Andor API ctypes shim found in
    rpc_acquisition.andor.andor.

    Note that rpc_acquisition.andor.andor.initialize(..) should be called once before
    instantiating this class.'''

    def __init__(self, property_server=None):
        self._callback_properties = {}
        
        self._add_enum('AuxiliaryOutSource', 'auxiliary_out_source')
        self._add_enum('AOIBinning', 'binning')
        self._add_enum('CycleMode', 'cycle_mode')
        self._add_enum('FanSpeed', 'fan')
        self._add_enum('IOSelector', 'io_selector')
        self._add_enum('SimplePreAmpGainControl', 'sensor_gain')
        self._add_enum('TriggerMode', 'trigger_mode')
        self._add_enum('TemperatureStatus', 'temperature_status', readonly=True)
        
        self._add_property('ExposureTime', 'exposure_time', 'Float')

        self._property_server = property_server
        if property_server:
            self._c_callback = andor.FeatureCallback(self._andor_callback)
            self._serve_properties = False
            for at_feature in self._callback_properties.keys():
                andor.RegisterFeatureCallback(at_feature, self._c_callback, 0)
            self._serve_properties = True

    def _add_enum(self, at_feature, py_name, readonly=False):
        if readonly:
            enum = ReadOnly_AT_Enum(at_feature)
        else:
            enum = AT_Enum(at_feature)
        self._callback_properties[at_feature] = (enum.get_value, py_name)
        setattr(self, py_name, enum)

    def _add_property(self, at_feature, py_name, at_type, readonly=False):
        andor_getter = getattr(andor, 'Get'+at_type)
        def getter():
            return andor_getter(at_feature)
        setattr(self, 'get_'+py_name, getter)
        self._callback_properties[at_feature] = (getter, py_name)
        
        if not readonly:
            andor_setter = getattr(andor, 'Set'+at_type)
            def setter(value):
                andor_setter(at_feature, value)
            setattr(self, 'set_'+py_name, setter)
            
    def _andor_callback(self, camera_handle, at_feature, context):
        if self._serve_properties:
            getter, py_name = self._callback_properties[at_feature]
            self._property_server.update_property(py_name, getter())
        return andor.AT_CALLBACK_SUCCESS

    def __del__(self):
        if self._property_server:
            for at_feature in self._callback_properties.keys():
                andor.UnregisterFeatureCallback(at_feature, self._c_callback, 0)