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
# Authors: Erik Hvatum, Zach Pincus

import threading
import time
import ctypes
import numpy
import contextlib
import collections
import atexit
import itertools

from . import lowlevel
from ...util import transfer_ism_buffer
from ...util import enumerated_properties
from ...util import property_device
from ...config import scope_configuration

class ReadOnly_AT_Enum(enumerated_properties.ReadonlyDictProperty):
    def __init__(self, feature):
        self._feature = feature
        super().__init__()

    def _get_hw_to_usr(self):
        return {i: lowlevel.GetEnumStringByIndex(self._feature, i)
            for i in range(lowlevel.GetEnumCount(self._feature))
            if lowlevel.IsEnumIndexImplemented(self._feature, i)}

    def _read(self):
        return lowlevel.GetEnumIndex(self._feature)

class AT_Enum(ReadOnly_AT_Enum, enumerated_properties.DictProperty):
    def get_values_validity(self):
        """Dict mapping value strings to True/False depending on whether that value
        may be assigned without raising an AndorError, given the camera's current state."""
        return {feature: lowlevel.IsEnumIndexAvailable(self._feature, i)
            for i, feature in self._hw_to_usr.items()}

    def _write(self, value):
        lowlevel.SetEnumIndex(self._feature, value)

class Camera(property_device.PropertyDevice):
    """This class provides an abstraction of the raw Andor API ctypes shim found in
    rpc_acquisition.andor.lowlevel."""

    _CAMERA_DEFAULTS = [
        ('AOIBinning', lowlevel.SetEnumString, '1x1'),
        ('AOILeft', lowlevel.SetInt, 1),
        ('AOITop', lowlevel.SetInt, 1),
        ('AOIWidth', lowlevel.SetInt, 2560),
        ('AOIHeight', lowlevel.SetInt, 2160),
        ('AccumulateCount', lowlevel.SetInt, 1),
        ('AuxiliaryOutSource', lowlevel.SetEnumString, 'FireAll'),
        ('TriggerMode', lowlevel.SetEnumString, 'Internal'), # need to set internal trigger mode to be able to set overlap and exposure time
        ('CycleMode', lowlevel.SetEnumString, 'Fixed'),
        ('ElectronicShutteringMode', lowlevel.SetEnumString, 'Global'),
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
        ('MetadataEnable', lowlevel.SetBool, True),
        ('MetadataTimestamp', lowlevel.SetBool, True),
        ('Overlap', lowlevel.SetBool, False),
        ('PixelReadoutRate', lowlevel.SetEnumString, '100 MHz'),
        ('SensorCooling', lowlevel.SetBool, True),
        ('SimplePreAmpGainControl', lowlevel.SetEnumString, '16-bit (low noise & high well capacity)'),
        ('SpuriousNoiseFilter', lowlevel.SetBool, True),
        ('StaticBlemishCorrection', lowlevel.SetBool, True),
        ('TriggerMode', lowlevel.SetEnumString, 'Software'), # now back to software triggering
        #('VerticallyCenterAOI', lowlevel.SetBool, False)
    ]

    _PROPERTIES_THAT_CAN_CHANGE_FRAME_RATE_RANGE = set([
        'AOITop',
        'AOIHeight',
        'PixelReadoutRate',
        'ElectronicShutteringMode',
        'TriggerMode',
        'Overlap',
        'ExposureTime'
    ])

    def __init__(self, property_server=None, property_prefix=''):
        super().__init__(property_server, property_prefix)
        # _callback_properties maps Andor property names (CamelCase) to (getter, update) pairs,
        # where getter() is a function that retrieves the current value for that property, and
        # update(value) posts the new value to the property server.
        self._callback_properties = {}
        # _andor_property_types maps Python property names (underbar_separated) to a pair of:
        # Andor property type (Int, Bool, Float, or Enum), and a bool for whether the property
        # is read-only. This information is useful for programmatically constructing
        # GUI widgets representing each property.
        self._andor_property_types = {}

        config = scope_configuration.get_config()

        lowlevel.initialize(config.Camera.MODEL) # safe to call this multiple times

        self._live_mode = False
        self.return_to_default_state()

        # Expose some certain camera properties presented by the Andor API more or less directly,
        # the only transformation being translation of enumeration indexes to descriptive strings
        # for convenience
        self._add_andor_enum('AuxiliaryOutSource', 'auxiliary_out_source')
        self._add_andor_enum('AOIBinning', 'binning')
        self._add_andor_enum('BitDepth', 'bit_depth', readonly=True)
        self._add_andor_enum('CycleMode', 'cycle_mode')
        self._add_andor_enum('FanSpeed', 'fan', readonly=True)
        self._add_andor_enum('IOSelector', 'io_selector')
        self._add_andor_enum('PixelEncoding', 'pixel_encoding', readonly=True)
        self._add_andor_enum('PixelReadoutRate', 'readout_rate')
        self._gain_enum = self._add_andor_enum('SimplePreAmpGainControl', 'sensor_gain') # need to stash _gain_enum for custom setter defined below
        self._add_andor_enum('ElectronicShutteringMode', 'shutter_mode')
        self._add_andor_enum('TriggerMode', 'trigger_mode')
        self._add_andor_enum('TemperatureStatus', 'temperature_status', readonly=True)

        # Directly expose certain plain camera properties from Andor API
        self._add_andor_property('AccumulateCount', 'accumulate_count', 'Int')
        self._add_andor_property('AOIHeight', 'aoi_height', 'Int')
        self._add_andor_property('AOILeft', 'aoi_left', 'Int')
        self._add_andor_property('AOIStride', 'aoi_stride', 'Int', readonly=True)
        self._add_andor_property('AOITop', 'aoi_top', 'Int')
        self._add_andor_property('AOIWidth', 'aoi_width', 'Int')
        self._add_andor_property('CameraAcquiring', 'is_acquiring', 'Bool', readonly=True)
        self._add_andor_property('CameraModel', 'model_name', 'String', readonly=True)
        self._add_andor_property('FrameCount', 'frame_count', 'Int')
        self._add_andor_property('FrameRate', 'frame_rate', 'Float')
        self._add_andor_property('ImageSizeBytes', 'image_byte_count', 'Int', readonly=True)
        self._add_andor_property('InterfaceType', 'interface_type', 'String', readonly=True)
        self._add_andor_property('IOInvert', 'selected_io_pin_inverted', 'Bool')
        self._add_andor_property('MaxInterfaceTransferRate', 'max_interface_fps', 'Float', readonly=True)
        self._add_andor_property('Overlap', 'overlap_enabled', 'Bool')
        self._add_andor_property('SerialNumber', 'serial_number', 'String', readonly=True)
        self._add_andor_property('SpuriousNoiseFilter', 'spurious_noise_filter_enabled', 'Bool')
        self._add_andor_property('StaticBlemishCorrection', 'static_blemish_correction_enabled', 'Bool')
        self._add_andor_property('TimestampClock', 'current_timestamp', 'Int', readonly=True)
        self._add_andor_property('TimestampClockFrequency', 'timestamp_hz', 'Int', readonly=True)
        self._add_andor_property('SensorCooling', 'sensor_cooling_enabled', 'Bool', readonly=True)
        self._add_andor_property('SensorTemperature', 'sensor_temperature', 'Float', readonly=True)

        #  custom getters and setters are defined for these features below
        self._add_property_data('ExposureTime', 'Float', False, 'exposure_time', self.get_exposure_time)
        self._add_property_data('ReadoutTime', 'Float', True, 'readout_time', self.get_readout_time)

        if property_server:
            self._c_callback = lowlevel.FeatureCallback(self._andor_callback)
            for at_feature in self._callback_properties.keys():
                lowlevel.RegisterFeatureCallback(at_feature, self._c_callback, 0)

            self._sleep_time = 10
            self._timer_running = True
            self._timer_thread = threading.Thread(target=self._timer_update_temp, daemon=True)
            self._timer_thread.start()

        self._frame_number = -1
        self._update_property('frame_number', self._frame_number)
        self._update_property('live_mode', self._live_mode)
        self._maybe_update_frame_rate_and_range('ExposureTime') # pretend exposure time was updated, to force the frame rate range to get updated
        self._latest_data = None
        self._latest_timestamp = None
        self._latest_image_lock = threading.Lock()

    def _timer_update_temp(self):
        getter, updater = self._callback_properties['SensorTemperature']
        while self._timer_running:
            updater(getter())
            time.sleep(self._sleep_time)

    def return_to_default_state(self):
        """Set the camera to its default, baseline state. Always a good idea to do before doing anything else."""
        try:
            self.set_live_mode(False)
        except:
            pass
        try:
            lowlevel.Command('AcquisitionStop')
        except:
            pass
        lowlevel.Flush()
        for feature, setter, value in self._CAMERA_DEFAULTS:
            setter(feature, value)

    def _add_property_data(self, at_feature, at_type, readonly, py_name, getter):
        updater = self._add_property(py_name, getter())
        self._callback_properties[at_feature] = (getter, updater)
        self._andor_property_types[py_name] = at_type, readonly

    def _add_andor_enum(self, at_feature, py_name, readonly=False, custom_setter=False):
        """Expose a camera setting presented by the Andor API as an enum (via GetEnumIndex,
        SetEnumIndex, and GetEnumStringByIndex) as an "enumerated" property."""
        if readonly:
            enum = ReadOnly_AT_Enum(at_feature)
        else:
            enum = AT_Enum(at_feature)
            setattr(self, 'get_'+py_name+'_values', enum.get_values_validity)
        setattr(self, 'get_'+py_name, enum.get_value)
        self._add_property_data(at_feature, 'Enum', readonly, py_name, enum.get_value)

        setter_name = 'set_'+py_name
        if not readonly and not hasattr(self, setter_name):
            def setter(value):
                with self.in_state(live_mode=False):
                    enum.set_value(value)
                    self._maybe_update_frame_rate_and_range(at_feature)
            setattr(self, setter_name, setter)
        return enum

    def _add_andor_property(self, at_feature, py_name, at_type, readonly=False):
        '''Directly expose numeric or string camera setting.'''
        andor_getter = getattr(lowlevel, 'Get'+at_type)
        def getter():
            # Value retrieval fails for certain properties, depending on camera state. For
            # example, GetInt('FrameCount') fails with the Andor NOTIMPLEMENTED error code
            # when CycleMode is Continuous. A camera property getter response or change
            # notification of value None may indicate that the property is not applicable
            # given the current camera state.
            try:
                return andor_getter(at_feature)
            except lowlevel.AndorError:
                return None
        setattr(self, 'get_'+py_name, getter)
        if at_type in ('Float', 'Int'):
            andor_min_getter = getattr(lowlevel, 'Get'+at_type+'Min')
            andor_max_getter = getattr(lowlevel, 'Get'+at_type+'Max')
            def range_getter():
                try:
                    min = andor_min_getter(at_feature)
                except lowlevel.AndorError:
                    min = None
                try:
                    max = andor_max_getter(at_feature)
                except lowlevel.AndorError:
                    max = None
                return min, max
            setattr(self, 'get_'+py_name+'_range', range_getter)
        self._add_property_data(at_feature, at_type, readonly, py_name, getter)

        if not readonly:
            andor_setter = getattr(lowlevel, 'Set'+at_type)
            def setter(value):
                with self.in_state(live_mode=False):
                    andor_setter(at_feature, value)
                    self._maybe_update_frame_rate_and_range(at_feature)
            setattr(self, 'set_'+py_name, setter)

    def _andor_callback(self, camera_handle, at_feature, context):
        getter, update = self._callback_properties[at_feature]
        update(getter())
        return lowlevel.AT_CALLBACK_SUCCESS

    def __del__(self):
        if self._property_server:
            for at_feature in self._callback_properties.keys():
                lowlevel.UnregisterFeatureCallback(at_feature, self._c_callback, 0)

    def get_andor_property_types(self):
        """Return a dict mapping the property names to a pair of:
        (andor_type, read_only), where andor_type is a one of 'Int', 'String',
        'Bool', 'Float', or 'Enum', and read_only is a boolean value."""
        return self._andor_property_types

    def _maybe_update_frame_rate_and_range(self, at_feature):
        """When setting a property, the frame rate range may change. If so,
        update the range and set the frame rate to the max possible."""
        if at_feature in self._PROPERTIES_THAT_CAN_CHANGE_FRAME_RATE_RANGE:
            min, max = self.get_frame_rate_range()
            self._update_property('frame_rate_range',  '[{:.5f}, {:.5f}]'.format(min, max))
            if lowlevel.IsWritable('FrameRate'):
                lowlevel.SetFloat('FrameRate', max)
                self._update_property('frame_rate', max)

    # STATE-STACK HANDLING
    # there are complex dependencies here. When pushing, better to set frame_count AFTER cycle_mode,
    # and trigger_mode AFTER exposure_time, and overlap_mode after all the things it depends on.
    # when popping, better to go in reverse order from setting the dependent parameters like overlap and frame_count.
    # Also, always better to set frame_rate last, because many things can change the available range.
    # In all cases, want to turn off live mode ASAP or turn it on only at the end.
    # NB: low-value weights cause the property to be set sooner. All non-named properties get zero weight
    def _get_push_weights(self, state):
        weights = dict(frame_count=1, trigger_mode=2, overlap_enabled=3, frame_rate=4) # high weight = done later
        if state.get('live_mode', False): # turning on live mode
            live_weight = 5 # turn on last
        else:
            live_weight = -1 # turn off first
        weights['live_mode'] = live_weight
        return weights

    def _get_pop_weights(self, state):
        weights = dict(frame_count=-1, trigger_mode=-2, overlap_enabled=-3, frame_rate=1) # low weight = done earlier
        if state.get('live_mode', False): # turning on live mode
            live_weight = 2 # turn on last
        else:
            live_weight = -4 # turn off first
        weights['live_mode'] = live_weight
        return weights

    def _update_push_states(self, state, old_state):
        super()._update_push_states(state, old_state)
        if state.get('overlap_enabled', False):
            # Setting overlap_enabled can clobber the exposure time,
            # so we need to make sure to save the existing exposure time.
            old_state['exposure_time'] = self.get_exposure_time()

    def get_readout_time(self):
        """Return sensor readout time in ms"""
        return 1000 * lowlevel.GetFloat('ReadoutTime')

    def get_exposure_time(self):
        """Return exposure time in ms"""
        return 1000 * lowlevel.GetFloat('ExposureTime')

    def set_exposure_time(self, ms):
        """Set the exposure time in ms. If necessary, live imaging will be paused."""
        lowlevel.SetFloat('ExposureTime', ms / 1000)
        self._maybe_update_frame_rate_and_range('ExposureTime')
        if self._live_mode:
            trigger_interval = self._calculate_live_trigger_interval()
            self._live_trigger.trigger_interval = trigger_interval
            self._live_reader.set_timeout(trigger_interval)
            # ... and clear recent FPS data
            self._live_reader.latest_intervals.clear()

    def get_exposure_time_range(self):
        """Return current exposure time minimum and maximum values in ms"""
        return (1000 * lowlevel.GetFloatMin('ExposureTime'),
                1000 * lowlevel.GetFloatMax('ExposureTime'))


    def set_sensor_gain(self, value):
        with self.in_state(live_mode=False):
            self._gain_enum.set_value(value)
            if value.startswith('12'):
                # make sure we always use the packed encoding for 12-bit mode
                lowlevel.SetEnumString('PixelEncoding', 'Mono12Packed')

    def get_aoi(self):
        """Convenience wrapper around the aoi_left, aoi_top, aoi_width, aoi_height
        properties. When setting this property, None elements and omitted entries
        cause the corresponding aoi_* property to be left unmodified."""
        return {
            'aoi_left' : self.get_aoi_left(),
            'aoi_top' : self.get_aoi_top(),
            'aoi_width' : self.get_aoi_width(),
            'aoi_height' : self.get_aoi_height()
        }

    def get_aoi_shape(self):
        """Return shape of the images the camera is acquiring as a (width, height) tuple."""
        return self.get_aoi_width(), self.get_aoi_height()

    def _delta_sort_key(self, kv):
        key, value = kv
        return value - getattr(self, 'get_'+key)()

    def set_aoi(self, aoi_dict):
        # Although this property gives the appearence of setting multiple AOI parameters simultaneously,
        # each parameter is actually sent to the layer beneath us one at a time, and it is never permitted
        # to (even temporarily) specify an illegal AOI.
        #
        # Consider that {'aoi_left' : 2001, 'aoi_width' : 500} specifies horizontal AOI parameters that
        # are valid together. However, if aoi_left is greater than 2061 before the change, aoi_left
        # must be updated before aoi_width.
        #
        # Performing AOI updates in ascending order of signed parameter value change ensures that setting
        # a collection of AOI parameters that are together legal does not require transitioning through
        # an illegal state.
        with self.in_state(live_mode=False):
            for key, value in sorted(aoi_dict.items(), key=self._delta_sort_key):
                getattr(self, 'set_' + key)(value)

    def full_aoi(self):
        """Set the AOI to full frame"""
        # set AOI in steps. First, set the top and left to the origin. This way,
        # queries to get_aoi_[width|height]_range will return the maximum possible size.
        # Otherwise, they will only return the valid range given the current left/top position.
        self.set_aoi_left(1)
        self.set_aoi_top(1)
        self.set_aoi_width(self.get_aoi_width_range()[1])
        self.set_aoi_height(self.get_aoi_height_range()[1])

    def vertically_center_aoi(self):
        l, h = self.get_aoi_top_range()
        self.set_aoi_top(int((l+h)/2))

    def get_safe_image_count_to_queue(self):
        """Return the maximum number of images that can be safely left on the camera head
        before overflowing its limited memory.

        This depends ONLY on the AOI, and specifically only on the maximum amount that the
        AOI is above or below the midline. (Ergo, each half-sensor readout chip must have its
        own RAM.) It depends not at all on the binning or bit depth.

        The dependence is a bit weird, but the formula was derived empirically and
        fits the actual data very closely:
            safe_images_to_queue = 126464 / max_lines + 29
        where max_lines is the maximum number of sensor lines to be read above or below
        the midline. Note that to give a safety factor here, we actually use 20 in the
        formula above...
        """
        binning = int(self.get_binning()[0])
        height = self.get_aoi_height() * binning # binning doesn't change this
        top = self.get_aoi_top() * binning - 1 # convert to zero-based indexing
        bottom = top + height
        if bottom < 1080 or top > 1080: # all above or all below
            lines = height
        else: # spans midline
            above = 1080 - top
            below = bottom - 1080
            lines = max(above, below)
        return int(126464 / lines + 20) # use 20 here instead of 29 to give a safety factor...

    def reset_timestamp(self):
        """Reset timestamp clock to zero."""
        lowlevel.Command('TimestampClockReset')

    def get_live_mode(self):
        return self._live_mode

    def set_live_mode(self, enabled):
        if enabled:
            self._enable_live()
        else:
            self._disable_live()
        self._update_property('live_mode', enabled)

    def latest_image(self):
        """Get the latest image that the camera retrieved."""
        # Return the name of the shared memory buffer that the latest live image
        # was stored in. The scope_client code will transparently retrieve the
        # image bytes based on this name, either via the ISM_Buffer mechanism if
        # the client is on the same machine, or over the network.
        with self._latest_image_lock:
            if self._latest_data is None:
                raise RuntimeError('No image has been acquired.')
            name, array, self._latest_timestamp = self._latest_data
            transfer_ism_buffer.server_register_array_for_transfer(name, array)
            return name

    def _update_image_data(self, name, array, timestamp):
        """Update information about the latest image, and broadcast to the world
        that another image has been retrieved."""
        self._latest_data = name, array, timestamp
        self._frame_number += 1
        self._update_property('frame_number', self._frame_number)

    def _enable_live(self):
        """Turn on live-imaging mode. The basic strategy is to put the camera
        into software triggering mode with continuous cycling and then have a
        thread that simply executes a software trigger at the maximum possible
        rate given how fast the camera can operate (as determined by the logic
        in _calculate_live_trigger_interval()). A single buffer is created and
        repeatedly queued and waited on by a separate thread, which exists to
        copy the result out to the output array via convert_buffer() as fast as
        possible. Note that tight coupling between the trigger and the reader
        threads is not required, as the camera has some RAM in which images
        that have been acquired can be buffered before getting read out to the
        computer via the Andor queue / wait commands."""
        if self._live_mode:
            return
        lowlevel.Flush()
        self.push_state(cycle_mode='Continuous', trigger_mode='Software', readout_rate='280 MHz')
        trigger_interval = self._calculate_live_trigger_interval()
        namebase = 'live@-'+str(time.time())
        buffer_maker = BufferFactory(namebase, frame_count=1, cycle=True)
        self._live_mode = True
        lowlevel.Command('AcquisitionStart')
        def update():
            self._update_image_data(*buffer_maker.convert_buffer())
        self._live_reader = LiveReader(buffer_maker.queue_buffer, update, trigger_interval)
        self._live_trigger = LiveTrigger(trigger_interval, self._live_reader)

    def _calculate_live_trigger_interval(self):
        """Determine how long to wait between sending acquisition triggers in
        live mode, based on data from the andor API.
        Returns trigger interval in seconds."""
        sustainable_rate = min(self.get_frame_rate(), self.get_max_interface_fps())
        trigger_interval = 1/sustainable_rate * 1.05
        return trigger_interval

    def _disable_live(self):
        if not self._live_mode:
            return
        # stop the reader thread first: otherwise, with no triggering, the reader
        # thread won't stop until the WaitBuffer operation times out, which is
        # by definition a tad slow. But if the reader is stopped while triggering
        # is still ongoing, then it can read one last frame quickly and stop.
        self._live_reader.stop()
        self._live_trigger.stop()
        lowlevel.Command('AcquisitionStop')
        lowlevel.Flush()
        self._live_mode = False
        self.pop_state()

    def get_live_fps(self):
        if not self._live_mode:
            return
        if not self._live_reader.latest_intervals:
            # no intervals yet
            return 0
        return 1/numpy.mean(self._live_reader.latest_intervals)

    def acquire_image(self, **camera_params):
        """Acquire a single image from the camera, with its current settings.
        NB: This is a SLOW way to acquire multiple images. In that case,
        use the start_image_sequence_acquisition(), next_image(), and
        end_image_sequence_acquisition() functions, with software/internal/external
        triggering as appropriate."""
        self.start_image_sequence_acquisition(frame_count=1, **camera_params)
        read_timeout_ms = self.get_exposure_time() + 1000 # exposure time + 1 second
        name = self.next_image(read_timeout_ms)
        self.end_image_sequence_acquisition()
        return name

    def send_software_trigger(self):
        """Send a software trigger command to the camera to start an acquisition.
        Only valid when used between start_image_sequence_acquisition() and
        end_image_sequence_acquisition() commands, when the camera's trigger_mode is
        set to 'Software'."""
        lowlevel.Command('SoftwareTrigger')

    def start_image_sequence_acquisition(self, frame_count=1, trigger_mode='Internal', **camera_params):
        """Start acquiring a sequence of a given number of images.

        Parameters
            frame_count: the number of images that will be obtained. If None,
                the camera is placed into "continuous" acquisition mode. In this
                case, if the camera is in "Internal" triggering mode, the camera
                can easily fill its internal RAM with image data faster than the
                user can retrieve images with next_image(), so care must be taken
                to limit the frame rate or the amount of time that images are
                acquired for.
            trigger_mode: Must be a valid trigger_mode string ('Internal', 'Software',
                'External', or 'ExternalExposure'). Most uses will use one of:
                 - 'Internal' triggering, in which the camera acquires images either
                as fast as possible (exposure_time < read_time), or at the rate
                specified by frame_rate; or
                 - 'Software' triggering, where new acquisitions are triggered via
                the send_software_trigger() command; or
                 - 'External', where new acquisitions are triggered via TTL pulses
                (usually from the IOTool box); or
                 - 'ExternalExposure', where TTL pulses determine the exposure time.
            All other keyword arguments will be used to set the camera state (e.g.
            exposure_time, readout_rate, etc.)
        After starting an image sequence, next_image() can be called to retrieve
        images from the camera, and after all images have been received,
        end_image_sequence_acquisition() will properly clean up the acquisition
        state.

        """
        if frame_count == 1:
            namebase = 'acquire@'+str(time.time())
        else:
            namebase = 'sequence@{}-'.format(time.time())
        if frame_count is None:
            cycle_mode = 'Continuous'
        else:
            cycle_mode = 'Fixed'
            camera_params['frame_count'] = frame_count
        self.push_state(live_mode=False, cycle_mode=cycle_mode, trigger_mode=trigger_mode, **camera_params)
        lowlevel.Flush()
        self._buffer_maker = BufferFactory(namebase, frame_count=frame_count, cycle=False)
        if frame_count is not None:
            # if we have a known number of images to acquire, create and queue buffers for them now.
            # however, don't queue up more than a gig or so of images
            max_queue = int(1024**3 / self.get_image_byte_count())
            for i in range(min(max_queue, frame_count)):
                self._buffer_maker.queue_buffer()
        lowlevel.Command('AcquisitionStart')

    def next_image(self, read_timeout_ms=lowlevel.ANDOR_INFINITE):
        """Retrieve the next image from the image acquisition sequence. Will block
        if the image has not yet been triggered or retrieved from the camera.
        If a timeout is provided, either an image will be returned within that time
        or an AndorError of TIMEDOUT will be raised."""
        self._buffer_maker.queue_if_needed()
        lowlevel.WaitBuffer(int(round(read_timeout_ms)))
        self._update_image_data(*self._buffer_maker.convert_buffer())
        return self.latest_image()

    def get_latest_timestamp(self):
        """Return the timestamp of the most recent image acquired."""
        if self._latest_timestamp is not None:
            return int(self._latest_timestamp)

    def end_image_sequence_acquisition(self):
        """Stop an image-acquisition sequence and perform necessary cleanup."""
        lowlevel.Command('AcquisitionStop')
        lowlevel.Flush()
        self.pop_state()
        del self._buffer_maker


    def calculate_streaming_mode(self, frame_count, desired_frame_rate, **camera_params):
        """Determine the best-possible frame rate for a streaming acquisition of
        the given number of frames.

        Parameters:
            frame_count: number of frames to acquire
            desired_frame_rate: desired frames per second to acquire at
            All other keyword arguments will be used to set the camera state (e.g.
            exposure_time, readout_rate, etc.)

        Returns: frame_rate, overlap
           frame_rate is the closest frame rate to the one desired
           overlap is whether overlap mode must be enabled ir disabled to allow the requested frame rate

        """
        # possible options for Rolling Shutter: internal with or without overlap
        # possible options for Global Shutter: internal with or without overlap (long exposures) or internal without overlap (short exposures)
        with self.in_state(live_mode=False, **camera_params):
            if frame_count > self.get_safe_image_count_to_queue():
                live_fps = self.get_max_interface_fps()
                frame_rate = min(live_fps, desired_frame_rate)
            else:
                frame_rate = desired_frame_rate
            # NB: setting overlap mode in global shutter mode with a short exposure has the effect of setting the exposure time to
            # the readout time. So don't do this! Also can't use overlap mode with Rolling Shutter software triggering.
            try_overlap = True
            if self.get_shutter_mode() == 'Global' and desired_trigger_interval > self.readout_time():
                try_overlap = False
            if self.get_shutter_mode() == 'Rolling' and self.get_trigger_mode() == 'Software':
                try_overlap = False

            with self.in_state(overlap_enabled=False):
                non_overlap_min, non_overlap_max = self.get_frame_rate_range()
            if frame_rate < non_overlap_min: # non_overlap_min is always the lowest possible frame rate
                frame_rate = non_overlap_min
            if try_overlap:
                with self.in_state(overlap_enabled=True):
                    overlap_min, overlap_max = self.get_frame_rate_range()
                if frame_rate > overlap_max: # overlap_max is always the highest possible frame rate
                    frame_rate = overlap_max
                if overlap_min <= frame_rate <= overlap_max:
                    overlap = True
                else:
                    overlap = False
            else:
                if frame_rate > non_overlap_max:
                    frame_rate = non_overlap_max
                overlap = False
        return frame_rate, overlap


    def stream_acquire(self, frame_count, frame_rate, **camera_params):
        """Acquire a given number of images at the specified frame rate, or
        as fast as possible if the frame rate is unattainable given the current
        camera configuration. Overlap mode should not be specified as a camera
        param, because this function will automatically determine whether it
        should be used.

        If possible rolling shutter mode and the maximum possible readout rate
        should be used to optimize frame rates.

        Parameters:
            frame_count: number of frames to acquire
            frame_rate: frames per second to acquire at (if possible)
            All other keyword arguments will be used to set the camera state (e.g.
            exposure_time, readout_rate, etc.)

        Returns: images, timestamps, attempted_frame_rate

        """
        frame_rate, overlap = self.calculate_streaming_mode(frame_count, frame_rate,
            trigger_mode='Internal', **camera_params)
        self.start_image_sequence_acquisition(frame_count, frame_rate=frame_rate,
            trigger_mode='Internal', overlap_enabled=overlap, **camera_params)
        image_names = []
        timestamps = []
        read_time = 1/self.get_max_interface_fps()
        for _ in range(frame_count):
            image_names.append(self.next_image(3 * read_time * 1000))
            timestamps.append(self._latest_timestamp)
        self.end_image_sequence_acquisition()
        return image_names, timestamps, frame_rate


UINT8_P = ctypes.POINTER(ctypes.c_uint8)

class BufferFactory:
    def __init__(self, namebase, frame_count=1, cycle=False):
        width, height, stride = map(lowlevel.GetInt, ('AOIWidth', 'AOIHeight', 'AOIStride'))
        self.buffer_shape = (width, height)
        input_encoding = lowlevel.GetEnumStringByIndex('PixelEncoding', lowlevel.GetEnumIndex('PixelEncoding'))
        self.convert_buffer_args = (width, height, stride, input_encoding, 'Mono16')
        image_bytes = lowlevel.GetInt('ImageSizeBytes')
        self.queued_buffers = collections.deque()
        if cycle:
            self.buffers = itertools.cycle([numpy.empty(image_bytes, dtype=numpy.uint8) for i in range(frame_count)])
        else:
            self.buffers = self._new_buffer_iter(image_bytes, frame_count)
        if frame_count == 1 and not cycle:
            self.names = iter([namebase])
        else:
            self.names = self._name_iter(namebase)

    def _new_buffer_iter(self, image_bytes, frame_count):
        i = 0
        while True:
            i += 1
            yield numpy.empty(image_bytes, dtype=numpy.uint8)
            if frame_count is not None and i == frame_count:
                return

    def _name_iter(self, namebase):
        i = 0
        while True:
            yield namebase + str(i)
            i += 1

    def queue_buffer(self):
        buffer = next(self.buffers)
        lowlevel.QueueBuffer(buffer.ctypes.data_as(UINT8_P), len(buffer))
        self.queued_buffers.append(buffer)

    def queue_if_needed(self):
        if not self.queued_buffers:
            self.queue_buffer()

    def convert_buffer(self):
        name = next(self.names)
        output_array = transfer_ism_buffer.server_create_array(name, shape=self.buffer_shape,
            dtype=numpy.uint16, order='Fortran')
        buffer = self.queued_buffers.popleft()
        timestamp = parse_buffer_metadata(buffer, 1) # timestamp is metadata CID 1
        if timestamp is not None:
            timestamp = timestamp.view('<u8')[0] # timestamp is 8 bytes of little-endian unsigned int
        lowlevel.ConvertBuffer(buffer.ctypes.data_as(UINT8_P), output_array.ctypes.data_as(UINT8_P),
            *self.convert_buffer_args)
        return name, output_array, timestamp

def parse_buffer_metadata(buffer, desired_id):
    offset = len(buffer)
    while offset > 0:
        # chunk layout: [chunk][CID][length], where CID and length are 4-byte little-endian uints,
        # and where length is the size in bytes of chunk+CID.
        length_start = offset - 4
        cid_start = length_start - 4
        length = buffer[length_start:offset].view('<u4')[0]
        chunk_id = buffer[cid_start:length_start].view('<u4')[0]
        chunk_start = length_start - length # length includes CID and data
        if chunk_id == desired_id:
            return buffer[chunk_start:cid_start]
        offset = chunk_start
    return None

class LiveModeThread(threading.Thread):
    """Superclass for the threads that are used to run live camera acquisition,
    providing a basic API whereby the threads can be stopped manually, or if
    left running until the interpreter exits, the threads stop themselves."""
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
        # Without stopping running live-mode threads at exit, the
        # weakref.finalize() machinery (which also uses atexit) will tear apart
        # the ISM_Buffer array still in use by the LiveReader, leading to segfaults.
        # By registering this atexit AFTER the ISM_Buffer is constructed,
        # we guarantee that the thread will be caused to exit BEFORE
        # the ISM_Buffer finalization process (because atexit calls happen in
        # reverse order as they were registered: a LIFO queue.)
        atexit.register(self.stop)
        self.start()

    def stop(self):
        """Ask that the thread's execution stop and block until the thread complies."""
        self.running = False
        self.join()

    def run(self):
        try:
            while self.running:
                self.loop()
        # got to unregister the stop() method, otherwise that reference
        # to this thread object will stay around until interpreter exit, and thus
        # any resources held by the thread (i.e. ISM_Buffer-backed arrays) won't
        # be automatically released.
        finally:
            atexit.unregister(self.stop)

    def loop(self):
        raise NotImplementedError()

class LiveTrigger(LiveModeThread):
    def __init__(self, trigger_interval, live_reader):
        self.trigger_interval = trigger_interval
        self.trigger_count = 0 # number of triggers
        self.live_reader = live_reader
        super().__init__() # do this last b/c superclass auto-starts the thread on init

    def loop(self):
        """Sleep the prescribed sleep time and then send a software trigger.
        If the triggering gets too far ahead of image reading, stop sending
        triggers until the situation improves."""
        time.sleep(self.trigger_interval)
        if self.trigger_count - self.live_reader.image_count > 10:
            while self.trigger_count - self.live_reader.image_count > 1:
                # make sure that we break out of the loop if the thread is
                # asked to stop while we're waiting here:
                if not self.running:
                    return
                time.sleep(self.trigger_interval)
        lowlevel.Command('SoftwareTrigger')
        self.trigger_count += 1


class LiveReader(LiveModeThread):
    def __init__(self, queue_buffer, update, trigger_interval):
        """Repeatedly queue a buffer with the given queue_buffer() function,
        wait for it to be filled via the Andor API, then call
        update() which (presumably) will deal with the buffer
        contents. The argument image_count is the index of the frame retrieved
        since the start of this round of live imaging.
        NB: update() is called in this background thread, so any operations
        therein must be thread-safe."""
        self.queue_buffer = queue_buffer
        self.update = update
        self.latest_intervals = collections.deque(maxlen=10) # cyclic buffer containing intervals between recent image reads (for FPS calculations)
        self.image_count = 0 # number of frames retrieved
        self.ready = threading.Event()
        self.set_timeout(trigger_interval)
        self.timeout_count = 0
        super().__init__()
        self.ready.wait() # don't return from init until a buffer is queued

    def set_timeout(self, trigger_interval):
        self.timeout = int(1000 * trigger_interval) * 3 # convert to ms and triple for safety margin

    def loop(self):
        t = time.time()
        self.queue_buffer()
        self.ready.set()
        try:
            # with no timeout, we would have to make sure to stop the reader thread before
            # the trigger thread -- otherwise the reader would just block forever waiting
            # for a trigger to come. So set a reasonably-long timeout.
            lowlevel.WaitBuffer(self.timeout)
            self.timeout_count = 0
        except lowlevel.AndorError as e:
            # one danger: if WaitBuffer starts timing out because of some error state other than
            # that the trigger thread was stopped (which is usually a prelude to this thread being
            # stopped), then this will silently swallow the exception. This can happen if the
            # camera RAM fills up without being emptied by QueueBuffer/WaitBuffer fast enough,
            # though the reader/trigger threads take efforts to avoid that case.
            # Thus, we error out if several timeouts happen in a row.
            if e.args[0] == 'TIMEDOUT':
                self.timeout_count += 1
                if self.timeout_count > 10:
                    raise AndorError('Live image retrieval timing out.')
                return
            else:
                raise
        self.update()
        self.image_count += 1
        self.latest_intervals.append(time.time() - t)

