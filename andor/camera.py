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
import threading
import time
import ctypes

import ism_blob

from .. import enumerated_properties
from . import lowlevel

class ReadOnly_AT_Enum(enumerated_properties.ReadonlyDictProperty):
    def __init__(self, feature):
        self._feature = feature
        super().__init__()

    def _get_hw_to_usr(self):
        str_count = lowlevel.GetEnumCount(self._feature)
        return {idx : lowlevel.GetEnumStringByIndex(self._feature, idx) for idx in range(str_count)}

    def _read(self):
        return lowlevel.GetEnumIndex(self._feature)

class AT_Enum(ReadOnly_AT_Enum, enumerated_properties.DictProperty):
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

    _CAMERA_DEFAULTS = [
        ('AOIBinning', lowlevel.SetEnum, '1x1'),
        ('AOIHeight', lowlevel.SetInt, 2160),
        ('AOILeft', lowlevel.SetInt, 1),
        ('AOITop', lowlevel.SetInt, 1),
        ('AOIWidth', lowlevel.SetInt, 2560),
        ('AccumulateCount', lowlevel.SetInt, 1),
        ('AuxiliaryOutSource', lowlevel.SetEnum, 'FireAll'),
        ('CycleMode', lowlevel.SetEnum, 'Fixed'),
        ('ElectronicShutteringMode', lowlevel.SetEnum, 'Rolling'),
        ('ExposureTime', lowlevel.SetFloat, 0.01),
        ('FanSpeed', lowlevel.SetEnum, 'On'),
        ('FrameCount', lowlevel.SetInt, 1),
        ('IOSelector', lowlevel.SetEnum, 'Fire 1'),
        ('IOInvert', lowlevel.SetBool, False),
        ('IOSelector', lowlevel.SetEnum, 'Fire N'),
        ('IOInvert', lowlevel.SetBool, False),
        ('IOSelector', lowlevel.SetEnum, 'Aux Out 1'),
        ('IOInvert', lowlevel.SetBool, False),
        ('IOSelector', lowlevel.SetEnum, 'Arm'),
        ('IOInvert', lowlevel.SetBool, False),
        ('IOSelector', lowlevel.SetEnum, 'External Trigger'),
        ('IOInvert', lowlevel.SetBool, False),
        ('MetadataEnable', lowlevel.SetBool, False),
        ('MetadataTimestamp', lowlevel.SetBool, True),
        ('Overlap', lowlevel.SetBool, True),
        ('PixelReadoutRate', lowlevel.SetEnum, '100 MHz'),
        ('SensorCooling', lowlevel.SetBool, True),
        ('SimplePreAmpGainControl', lowlevel.SetEnum, '16-bit (low noise & high well capacity)'),
        ('SpuriousNoiseFilter', lowlevel.SetBool, True),
        ('TriggerMode', lowlevel.SetEnum, 'Software'),
        ('VerticallyCenterAOI', lowlevel.SetBool, False)
    ]

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
        self._add_property('FrameCount', 'frame_count', 'Int')
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
        # FanSpeed and SensorCooling are presented as read-only to make it harder to accidentally
        # or ill-advisedly disable either.
        self._add_enum('FanSpeed', 'fan', readonly=True)
        self._add_property('SensorCooling', 'sensor_cooling_enabled', 'Bool', readonly=True)

        self._property_server = property_server
        self._property_prefix = property_prefix
        if property_server:
            self._c_callback = lowlevel.FeatureCallback(self._andor_callback)
            # TODO: figure out which property causes NOTIMPLEMENTED barf in live mode
            for at_feature in self._callback_properties.keys():
                lowlevel.RegisterFeatureCallback(at_feature, self._c_callback, 0)
            self._update_live_mode = property_server.add_property(self._property_prefix + 'live_mode')
            self._update_live_buffer = property_server.add_property(self._property_prefix + 'live_buffer')
            self._update_live_frame = property_server.add_property(self._property_prefix + 'live_frame')
        else:
            self._update_live_mode = self._update_live_frame = self._update_live_buffer = lambda x: None
        self._live_mode = False
        sellf._update_live_mode(false)
        self._live_frame = 0

        self.return_to_default_state()

    def return_to_default_state(self):
        for feature, setter, value in self._CAMERA_DEFAULTS:
            setter(feature, value)

    def _add_enum(self, at_feature, py_name, readonly=False):
        '''Expose a camera setting presented by the Andor API via GetEnumIndex, 
        SetEnumIndex, and GetEnumStringByIndex as an enumerated property.'''
        if readonly:
            enum = ReadOnly_AT_Enum(at_feature)
        else:
            enum = AT_Enum(at_feature)
        setattr(self, py_name, enum)
        self._callback_properties[at_feature] = (enum.get_value, py_name)

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
        getter, py_name = self._callback_properties[at_feature]
        self._property_server.update_property(self._property_prefix + py_name, getter())
        return lowlevel.AT_CALLBACK_SUCCESS

    def __del__(self):
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

    def _delta_sort_key(self, kv):
        key, value = kv
        return value - getattr(self, 'get_'+key)()
        
    def set_aoi(self, aoi_dict):
        assert set(aoi_dict.keys()).issubset({'aoi_left', 'aoi_top', 'aoi_width', 'aoi_height'})
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
        # an illegal state.
        aoi_list = [(key, value) for key, value in aoi_dict.items() if value is not None]
        for key, value in sorted(aoi_list, key = _delta_sort_key):
            getattr(self, 'set_' + key)(value)

    def software_trigger(self):
        '''Send software trigger.  Causes an exposure to be acquired and eventually
        written to a queued buffer when an acquisition sequence is in progress and
        trigger_mode is 'Software'.'''
        lowlevel.Command('SoftwareTrigger')

    def reset_timestamp(self):
        '''Reset current_timestamp to 0.'''
        lowlevel.Command('TimestampClockReset')

    def get_live_mode(self):
        return self._live_mode

    def set_live_mode(self, enabled):
        if enabled:
            self._enable_live()
        else:
            self._disable_live()
        self._live_mode = enabled
        self._update_live_mode(enabled)
        self._update_live_buffer(self._live_buffer_name)

    def _enable_live(self):
        if self._live_mode:
            return
        self._live_buffer_name = 'live@'+str(time.time())
        self._live_mode_manager = LiveMode(self._live_buffer_name, self._update_live_frame)
        
    def _disable_live(self):
        if not self._live_mode:
            return
        self._live_mode_manager.stop()
        self._live_buffer_name = None
    
    def get_live_buffer_name(self):
        return self._live_buffer_name
    

class LiveMode:
    def __init__(self, blob_name, frame_update, fps=None):
        if fps is None:
            fps = min(self.get_max_interface_fps(), self.get_frame_rate())
        sleep_time = 1 / (fps-0.5) # subtract 0.5 for safety margin
        width = lowlevel.GetInt('AOIWidth')
        height = lowlevel.GetInt('AOIHeight')
        self.ism_blob = ism_blob.ISM_Blob.new(blob_name, shape=(width, height), dtype=numpy.uint16, order='Fortran')
        output_buffer = ctypes.byref(self.ism_blob.data)
        lowlevel.Flush()
        self.old_mode = self.cycle_mode.get_value()
        self.cycle_mode.set_value('Continuous')
        lowlevel.Command('AcquisitionStart')
        self.live_reader = LiveReader(output_buffer, frame_update, sleep_time)
        self.live_trigger = LiveTrigger(sleep_time)
        

    def stop(self):
        self.live_trigger.stop()
        self.live_reader.stop()
        self.live_reader.join()
        self.live_trigger.join()
        lowlevel.Command('AcquisitionStop')
        self.cycle_mode.set_value(self.old_mode)
        

class LiveModeThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
        self.start()
    
    def stop(self):
        self.running = False
    
    def run(self):
        while self.running:
            self.loop()
    
    def loop(self):
        raise NotImplementedError()
    
class LiveTrigger(LiveModeThread):
    def __init__(self, sleep_time):
        self.sleep_time = sleep_time
        super().__init__()
        
    def loop(self):
        time.sleep(self.sleep_time)
        lowlevel.Command('SoftwareTrigger')

class LiveReader(LiveModeThread):
    def __init__(self, output_buffer, sequence_update, sleep_time):
        self.output_buffer = output_buffer
        self.sequence_update = sequence_update
        self.last_times = numpy.zeros(100)
        self.buffer = lowlevel.make_buffer()
        self.width = lowlevel.GetInt('AOIWidth')
        self.height = lowlevel.GetInt('AOIHeight')
        self.stride = lowlevel.GetInt('AOIStride')
        self.input_encoding = lowlevel.GetEnum('PixelEncoding')
        self.image_number = 0
        self.ready = threading.Event()
        self.timeout = int(1000 * 2 * sleep_time) # double the triggering sleep time and convert to ms
        super().__init__()
        self.ready.wait() # don't return from init until a buffer is queued
    
    def loop(self):
        t = time.time()
        lowlevel.queue_buffer(self.buffer)
        self.ready.set()
        try:
            lowlevel.WaitBuffer(self.timeout) # allowing for a timeout permits the thread to exit even if triggering is stopped in the middle of a wait
        except AndorError as e:
            if e.errtext == 'TIMEDOUT':
                return
            else:
                raise
        lowlevel.ConvertBuffer(self.buffer, self.output_buffer, self.width, self.height, 
            self.stride, self.input_encoding, 'Mono16')
        self.sequence_update(self.image_number)
        self.image_number += 1
        self.last_times[self.image_number % self.last_times.size] = time.time() - t
        

