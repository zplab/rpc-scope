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

from .. import enumerated_properties
from . import lowlevel

class ReadOnly_AT_Enum(enumerated_properties.DictProperty):
    def __init__(self, feature):
        self._feature = feature
        super().__init__()

    def _get_hw_to_usr(self):
        str_count = lowlevel.GetEnumCount(self._feature)
        return {idx : lowlevel.GetEnumStringByIndex(self._feature, idx) for idx in range(str_count)}

    def _read(self):
        return lowlevel.GetEnumIndex(self._feature)

class AT_Enum(ReadOnly_AT_Enum):
    def get_available_values(self):
        '''The currently accepted values.  This is the subset of recognized_values
        that may be assigned without raising a NOTIMPLEMENTED AndorError, given the
        camera model and its current state.'''
        return sorted((feature for idx, feature in self._hw_to_usr.items() if lowlevel.IsEnumIndexAvailable(self._feature, idx)))

    def _write(self, value):
        lowlevel.SetEnumIndex(self._feature, value)

class Camera:
    '''This class provides an abstraction of the raw Andor API ctypes shim found in
    rpc_acquisition.andor.lowlevel.'''

    def __init__(self, property_server=None, property_prefix=''):
        lowlevel.initialize() # safe to call this multiple times
        self._callback_properties = {}

        # Expose some certain camera properties presented by the Andor API more or less directly,
        # the only transformation being translation of enumeration indexes to descriptive strings
        # for convenience
        self._add_enum('AuxiliaryOutSource', 'auxiliary_out_source')
        self._add_enum('AOIBinning', 'binning')
        self._add_enum('BitDepth', 'bit_depth', readonly=True)
        self._add_enum('CycleMode', 'cycle_mode')
        self._add_enum('IOSelector', 'io_selector')
        self._add_enum('PixelEncoding', 'pixel_encoding', readonly=True)
        self._add_enum('PixelReadoutRate', 'pixel_readout_rate')
        self._add_enum('ElectronicShutteringMode', 'shutter_mode')
        self._add_enum('SimplePreAmpGainControl', 'sensor_gain')
        self._add_enum('TriggerMode', 'trigger_mode')
        self._add_enum('TemperatureStatus', 'temperature_status', readonly=True)
        
        # Directly expose certain plain camera properties from Andor API
        self._add_property('AccumulateCount', 'accumulate_count', 'Int')
        self._add_property('AOIHeight', 'aoi_height', 'Int')
        self._add_property('AOILeft', 'aoi_left', 'Int')
        self._add_property('AOIStride', 'aoi_stride', 'Int', readonly=True)
        self._add_property('AOITop', 'aoi_top', 'Int')
        self._add_property('AOIWidth', 'aoi_width', 'Int')
        self._add_property('BaselineLevel', 'baseline_level', 'Int', readonly=True)
        self._add_property('BytesPerPixel', 'bytes_per_pixel', 'Float', readonly=True)
        self._add_property('CameraAcquiring', 'is_acquiring', 'Bool', readonly=True)
        self._add_property('CameraModel', 'model_name', 'String', readonly=True)
        self._add_property('ExposureTime', 'exposure_time', 'Float')
        self._add_property('FrameCount', 'frame_count', 'Float')
        self._add_property('FrameRate', 'frame_rate', 'Float')
        self._add_property('ImageSizeBytes', 'image_byte_count', 'Int', readonly=True)
        self._add_property('InterfaceType', 'interface_type', 'String', readonly=True)
        self._add_property('IOInvert', 'selected_io_pin_inverted', 'Bool')
        self._add_property('MaxInterfaceTransferRate', 'max_interface_fps', 'Float', readonly=True)
        self._add_property('MetadataEnable', 'metadata_enabled', 'Bool')
        self._add_property('MetadataTimestamp', 'include_timestamp_in_metadata', 'Bool')
        self._add_property('Overlap', 'overlap_enabled', 'Bool')
        self._add_property('ReadoutTime', 'readout_time', 'Float', readonly=True)
        self._add_property('SerialNumber', 'serial_number', 'String', readonly=True)
        self._add_property('SpuriousNoiseFilter', 'spurious_noise_filter_enabled', 'Bool')
        self._add_property('TimestampClock', 'current_timestamp', 'Int', readonly=True)
        self._add_property('TimestampClockFrequency', 'timestamp_ticks_per_second', 'Int', readonly=True)

        # Andor API commands and also abstractions not corresponding directly to any one Andor API
        # camera property are implemented as member functions without a leading _.


        # Sensor cooling reduces image noise, improving the quality of results, at the cost of
        # supplying power to the Peltier junction unit within the camera that serves to cool the
        # sensor.  Sensor cooling is always off when a camera is opened via the Andor API, even
        # if the camera has not been power cycled in the time since a previous Andor API session
        # activated sensor cooling.
        #
        # The cost of failing to activate sensor cooling in terms of insiduous reduction of result
        # quality far outweighs the extra power usage required to maintain sensor cooling while
        # the camera is opened.  Therefore, our first order of business after setting up properties
        # is to enable sensor cooling and ensure that the camera cooling fan is also enabled (the
        # fan defaults to being enabled, but it is critically important that it is enabled if
        # sensor cooling is enabled, as the Peltier unit generates waste heat that would damage
        # the camera if allowed to accumulate - so we set and verify this).
        #
        # FanSpeed and SensorCooling are presented as read-only to make it harder to accidentally
        # or ill-advisedly disable either.  Removing or supplying False to the readonly arguments
        # of the two calling calls disabled this protection.
        self._add_enum('FanSpeed', 'fan', readonly=True)
        self._add_property('SensorCooling', 'sensor_cooling_enabled', 'Bool', readonly=True)

        self._property_server = property_server
        self._property_prefix = property_prefix
        if property_server:
            self._c_callback = lowlevel.FeatureCallback(self._andor_callback)
            self._serve_properties = False
            # TODO: figure out which property causes NOTIMPLEMENTED barf in live mode
            for at_feature in self._callback_properties.keys():
                lowlevel.RegisterFeatureCallback(at_feature, self._c_callback, 0)
            self._serve_properties = True

            self._publish_live_mode_enabled = self._property_server.add_property(self._property_prefix + 'live_mode_enabled', False)
            from .andor_image_server import ZMQAndorImageServer
            self._andor_image_server = ZMQAndorImageServer(self, self._property_server.context)
        else:
            self._publish_live_mode_enabled = None

        lowlevel.SetEnumString('FanSpeed', 'On')
        if lowlevel.GetEnumStringByIndex('FanSpeed', lowlevel.GetEnumIndex('FanSpeed')) != 'On':
            raise lowlevel.AndorError('Failed to turn on camera fan!')
        lowlevel.SetBool('SensorCooling', True)
        if not lowlevel.GetBool('SensorCooling'):
            raise lowlevel.AndorError('Failed to enable sensor cooling!')

    def _add_enum(self, at_feature, py_name, readonly=False):
        '''Expose a camera setting presented by the Andor API via GetEnumIndex, 
        SetEnumIndex, and GetEnumStringByIndex as an enumerated property.'''
        if readonly:
            enum = ReadOnly_AT_Enum(at_feature)
        else:
            enum = AT_Enum(at_feature)
        self._callback_properties[at_feature] = (enum.get_value, py_name)
        setattr(self, py_name, enum)

    def _add_property(self, at_feature, py_name, at_type, readonly=False):
        '''Directly expose numeric or string camera setting.'''
        andor_getter = getattr(lowlevel, 'Get'+at_type)
        def getter():
            # Value retrieval fails for certain properties, depending on camera state.  For
            # example, GetInt('FrameCount') fails with the Andor NOTIMPLEMENTED error code
            # when CycleMode is Continuous.  A camera property getter response or change
            # notification of value None may indicate that the property is not applicable
            # given the current camera state.
            try:
                return andor_getter(at_feature)
            except lowlevel.AndorError:
                return None
        setattr(self, 'get_'+py_name, getter)
        self._callback_properties[at_feature] = (getter, py_name)
        
        if not readonly:
            andor_setter = getattr(lowlevel, 'Set'+at_type)
            def setter(value):
                andor_setter(at_feature, value)
            setattr(self, 'set_'+py_name, setter)

    def _andor_callback(self, camera_handle, at_feature, context):
        if self._serve_properties:
            getter, py_name = self._callback_properties[at_feature]
            self._property_server.update_property(self._property_prefix + py_name, getter())
        return lowlevel.AT_CALLBACK_SUCCESS

    def __del__(self):
#       print('~~~~~~~~~~~~~~~~~~~~~~~~~~~Camera.__del__~~~~~~~~~~~~~~~~~~~~~~~~~~~')
        if self._property_server:
            for at_feature in self._callback_properties.keys():
                lowlevel.UnregisterFeatureCallback(at_feature, self._c_callback, 0)
                    
    def get_aoi(self):
        '''Convenience wrapper around the aoi_left, aoi_top, aoi_width, aoi_height
        properties.  When setting this property, None elements and omitted entries
        cause the corresponding aoi_* property to be left unmodified.'''
        return {
            'aoi_left' : self.get_aoi_left(),
            'aoi_top' : self.get_aoi_top(),
            'aoi_width' : self.get_aoi_width(),
            'aoi_height' : self.get_aoi_height()
        }

    def set_aoi(self, aoi_dict):
        valid_keys = ['aoi_left', 'aoi_top', 'aoi_width', 'aoi_height']
        extraneous = set(aoi_dict.keys()) - set(('aoi_left', 'aoi_top', 'aoi_width', 'aoi_height'))
        if extraneous:
            e = 'Invalid AOI dict key{} {} supplied.  '
            if len(extraneous) == 1:
                e = e.format('', "'{}'".format(extraneous.pop()))
            else:
                e = e.format('s', sorted(list(extraneous)))
            raise KeyError(e + 'AOI dict keys must be one of {}.'.format(valid_keys))
        # Although this property gives the appearence of setting multiple AOI parameters simultaneously,
        # each parameter is actually sent to the layer beneath us one at a time, and it is never permitted
        # to (even temporarily) specify an illegal AOI.
        #
        # Consider that {'aoi_left' : 2001, 'aoi_width' : 500} specifies horizontal AOI parameters that
        # are valid together.  However, if aoi_left is greater than 2061 before the change, aoi_left
        # must be updated before aoi_width.
        # 
        # Performing AOI updates in ascending order of signed parameter value change ensures that setting
        # a collection of AOI parameters that are together legal does not require transitioning through
        # an illegal state.*
        # 
        # Although processing of vertical and horizontal parameters via this algorithm
        # is separable, applying a sort to both together will never fail when separate processing would 
        # succeed, and vice versa.**
        #
        # * A too-fat mouse will not fit through a too-occluded portal.  However, the mouse may fit
        # _after_ decreasing the size of the occlusion.
        # 
        # ** Proof: the validity of a horizontal parameter depends only on the other horizontal
        # parameter and never either vertical parameter, as does the validity of a vertical
        # parameter, mutatis mutandis.  Therefore, only ordering of subset elements relative to other
        # elements of the same subset matters, and sorting the combined set preserves subset ordering
        # such that separating the sets after sorting yields identical results to sorting each separately.
        deltas = []
        for key, value in aoi_dict.items():
            if value is not None:
                deltas.append((key, value, value - getattr(self, 'get_' + key)()))
        deltas.sort(key=lambda kv: kv[2])
        for key, value, delta in deltas:
            getattr(self, 'set_' + key)(value)

    def software_trigger(self):
        '''Send software trigger.  Causes an exposure to be acquired and eventually
        written to a queued buffer when an acquisition sequence is in progress and
        trigger_mode is 'Software'.'''
        lowlevel.Command('SoftwareTrigger')

    def reset_timestamp(self):
        '''Reset current_timestamp to 0.'''
        lowlevel.Command('TimestampClockReset')

    def get_live_mode_enabled(self):
        return self._andor_image_server.in_live_mode

    def set_live_mode_enabled(self, live_mode_enabled):
        self._andor_image_server.in_live_mode = live_mode_enabled
        if self._publish_live_mode_enabled is not None:
            self._publish_live_mode_enabled(live_mode_enabled)
