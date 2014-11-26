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
import numpy
import contextlib
import collections

from .. import ism_buffer_utils

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
    def get_values_validity(self):
        """Dict mapping value strings to True/False demending whether that value
        may be assigned without raising a NOTIMPLEMENTED AndorError, given the
        camera model and its current state."""
        return {feature: lowlevel.IsEnumIndexAvailable(self._feature, idx) for idx, feature in self._hw_to_usr.items()}

    def _write(self, value):
        lowlevel.SetEnumIndex(self._feature, value)

class Camera:
    """This class provides an abstraction of the raw Andor API ctypes shim found in
    rpc_acquisition.andor.lowlevel."""

    _CAMERA_DEFAULTS = [
        ('AOIBinning', lowlevel.SetEnumString, '1x1'),
        ('AOIHeight', lowlevel.SetInt, 2160),
        ('AOILeft', lowlevel.SetInt, 1),
        ('AOITop', lowlevel.SetInt, 1),
        ('AOIWidth', lowlevel.SetInt, 2560),
        ('AccumulateCount', lowlevel.SetInt, 1),
        ('AuxiliaryOutSource', lowlevel.SetEnumString, 'FireAll'),
        ('CycleMode', lowlevel.SetEnumString, 'Fixed'),
        ('ElectronicShutteringMode', lowlevel.SetEnumString, 'Rolling'),
        ('ExposureTime', lowlevel.SetFloat, 0.01),
        ('FanSpeed', lowlevel.SetEnumString, 'On'),
        ('FrameCount', lowlevel.SetInt, 1),
        ('IOSelector', lowlevel.SetEnumString, 'Fire 1'),
        ('IOInvert', lowlevel.SetBool, False),
        ('IOSelector', lowlevel.SetEnumString, 'Fire N'),
        ('IOInvert', lowlevel.SetBool, False),
        ('IOSelector', lowlevel.SetEnumString, 'Aux Out 1'),
        ('IOInvert', lowlevel.SetBool, False),
        ('IOSelector', lowlevel.SetEnumString, 'Arm'),
        ('IOInvert', lowlevel.SetBool, False),
        ('IOSelector', lowlevel.SetEnumString, 'External Trigger'),
        ('IOInvert', lowlevel.SetBool, False),
        ('MetadataEnable', lowlevel.SetBool, False),
        ('MetadataTimestamp', lowlevel.SetBool, True),
        ('Overlap', lowlevel.SetBool, False),
        ('PixelReadoutRate', lowlevel.SetEnumString, '100 MHz'),
        ('SensorCooling', lowlevel.SetBool, True),
        ('SimplePreAmpGainControl', lowlevel.SetEnumString, '16-bit (low noise & high well capacity)'),
        ('SpuriousNoiseFilter', lowlevel.SetBool, True),
        ('StaticBlemishCorrection', lowlevel.SetBool, True),
        ('TriggerMode', lowlevel.SetEnumString, 'Software'),
#        ('VerticallyCenterAOI', lowlevel.SetBool, False)
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
        self._add_property('StaticBlemishCorrection', 'static_blemish_correction_enabled', 'Bool')
        self._add_property('TimestampClock', 'current_timestamp', 'Int', readonly=True)
        self._add_property('TimestampClockFrequency', 'timestamp_ticks_per_second', 'Int', readonly=True)
        # FanSpeed and SensorCooling are presented as read-only to make it harder to accidentally
        # or ill-advisedly disable either.
        self._add_enum('FanSpeed', 'fan', readonly=True)
        self._add_property('SensorCooling', 'sensor_cooling_enabled', 'Bool', readonly=True)

        self._callback_properties['ExposureTime'] = (lowlevel.GetFloat, 'exposure_time') # we special case the getters and setters below
        
        self._property_server = property_server
        self._property_prefix = property_prefix
        if property_server:
            self._c_callback = lowlevel.FeatureCallback(self._andor_callback)
            for at_feature in self._callback_properties.keys():
                lowlevel.RegisterFeatureCallback(at_feature, self._c_callback, 0)
            self._update_live_mode = property_server.add_property(self._property_prefix + 'live_mode', False)
            self._update_live_frame = property_server.add_property(self._property_prefix + 'live_frame', None)
        else:
            self._update_live_mode = self._update_live_frame = lambda x: None
        self._live_mode = False
        self.return_to_default_state()
        self._state_stack = []

    def return_to_default_state(self):
        for feature, setter, value in self._CAMERA_DEFAULTS:
            setter(feature, value)

    @contextlib.contextmanager
    def _live_guarded(self):
        live = self._live_mode
        if live:
            self.set_live_mode(False)
        try:
            yield
        finally:
            if live:
            self.set_live_mode(True)

    def _add_enum(self, at_feature, py_name, readonly=False):
        """Expose a camera setting presented by the Andor API via GetEnumIndex, 
        SetEnumIndex, and GetEnumStringByIndex as an enumerated property."""
        if readonly:
            enum = ReadOnly_AT_Enum(at_feature)
            values_getter = enum.get_recognized_values
        else:
            enum = AT_Enum(at_feature)
            values_getter = enum.get_values_validity
        setattr(self, 'get_'+py_name, enum.get_value)
        setattr(self, 'get_'+py_name+'_values', values_getter)
        if not readonly:
            def setter(value):
                with self._live_guarded():
                    enum.set_value(value)
            setattr(self, 'set_'+py_name, setter)
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
                with self._live_guarded():
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
    
    def get_exposure_time(self):
        """Return exposure time in ms"""
        return 1000 * lowlevel.GetFloat('ExposureTime')
        
    def set_exposure_time(self, ms):
        live = self._live_mode
        if live: # pause live if we can't do fast exposure switching
            current_exposure = lowlevel.GetFloat('ExposureTime')
            read_time = self.get_readout_time()
            current_short = current_exposure < read_time
            new_short = ms < read_time
            must_pause_live = current_short != new_short
            if must_pause_live:
                self.set_live_mode(False)
        lowlevel.SetFloat('ExposureTime', ms / 1000)
        if live:
            if must_pause_live:
                self.set_live_mode(True)
            else:
                # changed exposure time without pausing live... update sleep time
                self._live_trigger.sleep_time = self._get_live_sleep_time()
                # ... and clear recent FPS data
                self._live_reader.last_times.clear() 
    
    def get_aoi(self):
        """Convenience wrapper around the aoi_left, aoi_top, aoi_width, aoi_height
        properties.  When setting this property, None elements and omitted entries
        cause the corresponding aoi_* property to be left unmodified."""
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

    def reset_timestamp(self):
        '''Reset current_timestamp to 0.'''
        lowlevel.Command('TimestampClockReset')

    def get_live_mode(self):
        return self._live_mode

    def set_live_mode(self, enabled):
        print("setting live mode", enabled)
        if enabled:
            self._enable_live()
        else:
            self._disable_live()
        self._update_live_mode(enabled)

    def get_live_image(self):
        ism_buffer_utils.server_register_array(self._live_buffer_name, self._live_array)
        return self._live_buffer_name

    def _enable_live(self):
        if self._live_mode:
            return
        self._live_buffer_name = 'live@'+str(time.time())
        lowlevel.Flush()
        self.push_state(overlap_enabled=False, cycle_mode='Continuous', trigger_mode='Software', pixel_readout_rate='280 MHz')
        sleep_time = self._get_live_sleep_time()
        input_buffer, self._live_array, convert_buffer = self._make_input_output_buffers(self._live_buffer_name)
        self._live_mode = True
        lowlevel.Command('AcquisitionStart')
        self._live_reader = LiveReader(input_buffer, convert_buffer, self._update_live_frame)
        self._live_trigger = LiveTrigger(sleep_time, self._live_reader)
    
    def _get_live_sleep_time(self):
        readout_time = self.get_readout_time()
        if self.get_exposure_time() / 1000 <= readout_time:
            frame_time = readout_time * 2
        else:
            frame_time = 1/self.get_frame_rate()
        sleep_time = max(1/self.get_max_interface_fps(), frame_time) * 1.05
        return sleep_time

    def _disable_live(self):
        if not self._live_mode:
            return
        self._live_buffer_name = None
        self._live_array = None
        self._live_trigger.stop()
        self._live_reader.stop()
        self._live_reader.join()
        self._live_trigger.join()
        lowlevel.Command('AcquisitionStop')
        lowlevel.Flush()
        self._live_mode = False
        self._update_live_frame(None)
        self.pop_state()
    
    def get_live_fps(self):
        if not self._live_mode:
            return
        return 1/numpy.mean(self._live_reader.last_times)
        
    def _make_input_output_buffers(self, name):
        width, height, stride = self.get_aoi_width(), self.get_aoi_height(), self.get_aoi_stride()
        input_encoding = self.get_pixel_encoding()
        output_array = ism_buffer_utils.server_create_array(name, shape=(width, height), dtype=numpy.uint16, 
            order='Fortran')
        input_buffer = lowlevel.make_buffer()
        def convert_buffer():
            lowlevel.ConvertBuffer(input_buffer, output_array.ctypes.data_as(lowlevel.uint8_p),
                width, height, stride, input_encoding, 'Mono16')
        return input_buffer, output_array, convert_buffer

    def _make_input_output_buffer_sequence(self, namebase, count):
        if count == 1:
            names = [namebase]
        else:
            names = [namebase + str(i) for i in range(count)]
        input_buffers, output_arrays, convert_buffers = zip(*map(self._make_input_output_buffers, names))
        return names, input_buffers, output_arrays, convert_buffers

    def acquire_image(self):
        read_timeout = int(self.get_exposure_time()) + 1000 # exposure time + 1 second
        self.start_image_sequence_acquisition(1)
        name = self.get_next_image(read_timeout)
        self.end_image_sequence_acquisition()
        return name
    
    def send_software_trigger(self):
        lowlevel.Command('SoftwareTrigger')
    
    def start_image_sequence_acquisition(self, frame_count, trigger_mode='Internal', **camera_params):
        if frame_count == 1:
            namebase = 'acquire@'+str(time.time())
        else:
            namebase = 'sequence@{}-'.format(time.time())
        live = self._live_mode
        self.set_live_mode(False)
        lowlevel.Flush()
        self.push_state(cycle_mode='Fixed', frame_count=frame_count, trigger_mode=trigger_mode, **camera_params)
        names, input_buffers, output_arrays, convert_buffers = self._make_input_output_buffer_sequence(namebase, frame_count)
        for ib in input_buffers:
            lowlevel.queue_buffer(ib)
        self._sequence_acquisition_state = SequenceAcquisitionState(live, names, output_arrays, convert_buffers)
        lowlevel.Command('AcquisitionStart')

    def get_next_image(self, read_timeout=lowlevel.ANDOR_INFINITE):
        name, output_array, convert_buffer = next(self._sequence_acquisition_state.acquire_data)
        lowlevel.WaitBuffer(read_timeout)
        convert_buffer()
        ism_buffer_utils.server_register_array(name, output_array)
        return name
        
    def end_image_sequence_acquisition(self):
        lowlevel.Command('AcquisitionStop')
        lowlevel.Flush()
        self.pop_state()
        self.set_live_mode(self._sequence_acquisition_state.live)
        del self._sequence_acquisition_state
            
    def set_state(self, **state):
        for k, v in state.items():
            getattr(self, 'set_'+k)(v)
    
    def push_state(self, **state):
        old_state = {k: getattr(self, 'get_'+k)() for k in state.keys()}
        self._state_stack.append(old_state)
        overlap = state.pop('overlap_enabled', None)
        self.set_state(**state)
        # overlap mode has complex dependencies, so it generally shouldn't be set until the very end
        if overlap is not None and lowlevel.IsWritable('Overlap'):
            self.set_overlap_enabled(overlap)
        
    def pop_state(self):
        old_state = self._state_stack.pop()
        overlap = old_state.pop('overlap_enabled', None)
        # overlap mode has complex dependencies, so it generally should be unset first
        if overlap is not None and lowlevel.IsWritable('Overlap'):
            self.set_overlap_enabled(overlap)
        self.set_state(**old_state)

class SequenceAcquisitionState:
    def __init__(self, live, names, output_arrays, convert_buffers):
        self.live = live
        self.acquire_data = zip(names, output_arrays, convert_buffers)        

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
    def __init__(self, sleep_time, live_reader):
        self.sleep_time = sleep_time
        self.trigger_count = 0 # number of triggers
        self.live_reader = live_reader
        super().__init__()
        
    def loop(self):
        time.sleep(self.sleep_time)
        if self.trigger_count - self.live_reader.image_count > 10:
            while self.trigger_count - self.live_reader.image_count > 1:
                if not self.running:
                    return
                time.sleep(self.sleep_time)
        lowlevel.Command('SoftwareTrigger')
        self.trigger_count += 1


class LiveReader(LiveModeThread):
    def __init__(self, input_buffer, convert_buffer, sequence_update):
        self.input_buffer = input_buffer
        self.convert_buffer = convert_buffer
        self.sequence_update = sequence_update
        self.last_times = collections.deque(maxlen=10)
        self.image_count = 0 # number of frames retrieved
        self.ready = threading.Event()
        super().__init__()
        self.ready.wait() # don't return from init until a buffer is queued
    
    def loop(self):
        t = time.time()
        lowlevel.queue_buffer(self.input_buffer)
        self.ready.set()
        try:
            lowlevel.WaitBuffer(500) # 500 ms timeout allowing for a timeout permits the thread to exit even if triggering is stopped in the middle of a wait
        except lowlevel.AndorError as e:
            if e.errtext == 'TIMEDOUT':
                return
            else:
                raise
        self.convert_buffer()
        self.last_times.append(time.time() - t)
        self.image_count += 1
        self.sequence_update(self.image_count)

