# This code is licensed under the MIT License (see LICENSE file for details)

"""
Andor Zyla camera modes are complex. There are several relevant parameters:

Rolling vs. Global shutter
Internal vs. Software triggering
Overlap mode
Exposure time with respect to sensor readout time

For rolling vs. global: when in doubt, use rolling shutter mode.
Global shutter is a bit of a hack, increasing readout noise and decreasing
frame rates. It's mainly useful when objects in the frame are moving fast
with respect to the frame readout time.

In internal triggering mode, the camera fires acquisitions off as specified by
the frame_rate parameter and the constraints below. In software triggering
mode, the user triggers acquisitions as required. Triggers that come faster
than the maximum frame rate will be ignored: they do not queue up! There are
also external triggering modes, which will not be discussed here but are used
by the IOTool device to sequence acquisitions.

In overlap mode, image readout and exposing the next image are overlapped;
in general this is a more efficient way to run the camera. However, for taking
image sequences with frame rates intentionally slower than the maximum,
non-overlap-mode may be required. Software triggering with rolling shutter
exposures is incompatible with overlap mode.

Frame rate constraints
----------------------
'exp' = exposure time
'read' = frame readout time
'delta' = some small time delta related to the sensor readout time.

Rolling Shutter, Internal Triggering
    overlap mode:      FPS range = [(1/exp + read), 1/(max(exp, read))]
    non-overlap mode:  FPS range = [0.00005, 1/(exp + read)]

Rolling Shutter, Software Triggering
    overlap mode disallowed.
    non-overlap mode: max trigger rate = 1/(exp + read)

Global Shutter, Internal or Software Triggering, exp < read
    overlap mode: setting overlap mode forcibly sets exp = read!
    non-overlap mode:  FPS range = [0.00005, 1/(exp + 2*read + delta)]

Global Shutter, Internal or Software Triggering, exp > read
    overlap mode:      FPS range = [0.00005, 1/(max(exp, 2*read) + delta)]
    non-overlap mode:  FPS range = [0.00005, 1/(exp + read + delta)]

NB: It is possible to switch into Global Shutter, Software Triggering mode
with exp < read, and then to modify the exposure time. However after switching
exp to a value > read, you can no longer switch back. Similarly, if Global
Shutter, Software Triggering mode is entered with exp > read, it is not possible
to switch to an exposure time < read. This is probably an andor bug.
TODO: check if the bug is still there in a future SDK release (date 2015-10)
"""

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
from ...util import property_device
from ...config import scope_configuration


from ...util import logging
logger = logging.get_logger(__name__)

class AndorEnum:
    def __init__(self, feature):
        self.feature = feature
        n = lowlevel.GetEnumCount(feature)
        self.index_to_value = {i: lowlevel.GetEnumStringByIndex(feature, i)
            for i in range(n) if lowlevel.IsEnumIndexImplemented(feature, i)}
        self.values = set(self.index_to_value.values())

    def get_value(self):
        return self.index_to_value[lowlevel.GetEnumIndex(self.feature)]

    def set_value(self, value):
        if value not in self.values:
            raise ValueError(f'Value must be one of: {sorted(self.values)}')
        lowlevel.SetEnumString(self.feature, value)

    def get_values_validity(self):
        """Dict mapping value strings to True/False depending on whether that value
        may be assigned without raising an AndorError, given the camera's current state."""
        return {value: lowlevel.IsEnumIndexAvailable(self.feature, i)
            for i, value in self.index_to_value.items()}

class AndorProp(dict):
    def __init__(self, at_feature, at_type, default=None, readonly=False):
        super().__init__(at_feature=at_feature, at_type=at_type, default=default, readonly=readonly)

class CameraBase(property_device.PropertyDevice):
    _DESCRIPTION = 'Andor camera'
    _EXPECTED_INIT_ERRORS = (lowlevel.AndorError,)
    _CAMERA_PROPERTIES = dict(
        aoi_height = AndorProp('AOIHeight', 'Int'),
        aoi_left = AndorProp('AOILeft', 'Int'),
        aoi_stride = AndorProp('AOIStride', 'Int', readonly=True),
        aoi_top = AndorProp('AOITop', 'Int'),
        aoi_width = AndorProp('AOIWidth', 'Int'),
        auxiliary_out_source = AndorProp('AuxiliaryOutSource', 'Enum', default='FireAll'),
        binning = AndorProp('AOIBinning', 'Enum', default='1x1'),
        bit_depth = AndorProp('BitDepth', 'Enum', readonly=True),
        current_timestamp = AndorProp('TimestampClock', 'Int', readonly=True),
        cycle_mode = AndorProp('CycleMode', 'Enum', default='Fixed'),
        exposure_time = AndorProp('ExposureTime', 'Float', default=10),
        fan = AndorProp('FanSpeed', 'Enum', readonly=True, default='On'),
        firmware_version = AndorProp('FirmwareVersion', 'String', readonly=True),
        frame_count = AndorProp('FrameCount', 'Int', default=1),
        frame_rate = AndorProp('FrameRate', 'Float'),
        image_byte_count = AndorProp('ImageSizeBytes', 'Int', readonly=True),
        interface_type = AndorProp('InterfaceType', 'String', readonly=True),
        io_selector = AndorProp('IOSelector', 'Enum'),
        is_acquiring = AndorProp('CameraAcquiring', 'Bool', readonly=True),
        max_interface_fps = AndorProp('MaxInterfaceTransferRate', 'Float', readonly=True),
        model_name = AndorProp('CameraModel', 'String', readonly=True),
        overlap_enabled = AndorProp('Overlap', 'Bool', default=True),
        pixel_encoding = AndorProp('PixelEncoding', 'Enum', readonly=True),
        pixel_height = AndorProp('PixelHeight', 'Float', readonly=True),
        pixel_width = AndorProp('PixelWidth', 'Float', readonly=True),
        readout_time = AndorProp('ReadoutTime', 'Float', readonly=True),
        row_read_time = AndorProp('RowReadTime', 'Float', readonly=True),
        selected_io_pin_inverted = AndorProp('IOInvert', 'Bool'),
        sensor_cooling_enabled = AndorProp('SensorCooling', 'Bool', default=True, readonly=True),
        sensor_height = AndorProp('SensorHeight', 'Float', readonly=True),
        sensor_temperature = AndorProp('SensorTemperature', 'Float', readonly=True),
        sensor_width = AndorProp('SensorWidth', 'Float', readonly=True),
        serial_number = AndorProp('SerialNumber', 'String', readonly=True),
        spurious_noise_filter_enabled = AndorProp('SpuriousNoiseFilter', 'Bool', default=True),
        temperature_status = AndorProp('TemperatureStatus', 'Enum', readonly=True),
        timestamp_hz = AndorProp('TimestampClockFrequency', 'Int', readonly=True),
        trigger_mode = AndorProp('TriggerMode', 'Enum')
    )
    _HIDDEN_PROPERTIES = (
        AndorProp('MetadataEnable', 'Bool', default=True),
        AndorProp('MetadataTimestamp', 'Bool', default=True)
    )
    _PROPERTIES_THAT_CAN_CHANGE_FRAME_RATE_RANGE = set([
        'AOITop',
        'AOIHeight',
        'PixelReadoutRate',
        'ElectronicShutteringMode',
        'TriggerMode',
        'Overlap',
        'ExposureTime'
    ])
    _GAIN_TO_ENCODING = None # to be filled by subclass
    _IO_PINS = None # to be filled by subclass
    _BASIC_PROPERTIES = None # minimal set of properties to concern oneself with (e.g. from a GUI), filled by subclass
    _UNITS = {
        'exposure_time': 'ms',
        'readout_time': 'ms',
        'max_interface_fps': 'fps',
        'frame_rate': 'fps',
        'frame_rate_range': 'fps',
        'sensor_temperature': '°C'
    }
    _MODEL_NAME = None # to be filled by subclass

    def __init__(self, property_server=None, property_prefix=''):
        super().__init__(property_server, property_prefix)
        config = scope_configuration.get_config()
        lowlevel.initialize(self._MODEL_NAME) # safe to call this multiple times
        self._live_mode = False

        # initialize properties
        # _updaters maps Andor property names to a function that will update the scope clients as to the new value
        # _defaulters is a list of functions to call to return the camera to the default state
        self._updaters = {}
        self._defaulters = []
        names_and_props = list(self._CAMERA_PROPERTIES.items())
        names_and_props += [(None, prop) for prop in self._HIDDEN_PROPERTIES]
        for py_name, prop in names_and_props:
            updater, defaulter = self._add_andor_property(py_name, **prop)
            if updater is not None:
                self._updaters[prop['at_feature']] = updater
            if defaulter is not None:
                self._defaulters.append(defaulter)
            if py_name == 'sensor_gain':
                # grab this property name for later use because it differs on different camera models
                self._set_sensor_gain_feature = prop['at_feature']

        self.return_to_default_state()

        if property_server:
            self._c_callback = lowlevel.FeatureCallback(self._andor_callback)
            for at_feature in self._updaters.keys():
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

    def _timer_update_temp(self):
        updater = self._updaters['SensorTemperature']
        while self._timer_running:
            updater()
            time.sleep(self._sleep_time)

    def _add_andor_property(self, py_name, at_feature, at_type, default, readonly):
        if at_type == 'Enum':
            getter, setter, valid = self._andor_enum(at_feature)
        else:
            getter, setter, valid = self._andor_property(at_feature, at_type)

        if py_name is None:
            updater = None
        else:
            getter_name = 'get_'+py_name
            setter_name = 'set_'+py_name
            if hasattr(self, getter_name):
                getter = getattr(self, getter_name)
            else:
                setattr(self, getter_name, getter)
            prop_update = self._add_property(py_name, getter())
            def updater():
                prop_update(getter())
            if valid is not None:
                valid_name = getter_name + valid[0]
                if not hasattr(self, valid_name):
                    setattr(self, valid_name, valid[1])
            if hasattr(self, setter_name):
                setter = getattr(self, setter_name)
            elif not readonly:
                setattr(self, setter_name, setter)

        if default is None:
            defaulter = None
        else:
            def defaulter():
                setter(default)
        return updater, defaulter

    def _andor_enum(self, at_feature):
        """Expose a camera setting presented by the Andor API as an enum (via GetEnumIndex,
        SetEnumIndex, and GetEnumStringByIndex) as an "enumerated" property."""
        enum = AndorEnum(at_feature)
        valid = '_values', enum.get_values_validity
        return enum.get_value, enum.set_value, valid

    def _andor_property(self, at_feature, at_type):
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
            valid = '_range', range_getter
        else:
            valid = None
        andor_setter = getattr(lowlevel, 'Set'+at_type)
        def setter(value):
            with self.in_state(live_mode=False):
                andor_setter(at_feature, value)
                self._maybe_update_frame_rate_and_range(at_feature)
        return getter, setter, valid

    def _andor_callback(self, camera_handle, at_feature, context):
        try:
            self._updaters[at_feature]()
        except:
            logger.log_exception('Error in andor callback:')
        return lowlevel.AT_CALLBACK_SUCCESS

    def __del__(self):
        if self._property_server:
            for at_feature in self._updaters.keys():
                lowlevel.UnregisterFeatureCallback(at_feature, self._c_callback, 0)

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
        self.set_trigger_mode('Internal') # overlap can't be set in software triggering mode
        for defaulter in self._defaulters:
            defaulter()
        self.set_trigger_mode('Software') # software is default triggering mode
        self.full_aoi()
        for io_pin in self._IO_PINS:
            lowlevel.SetEnumString('IOSelector', io_pin)
            lowlevel.SetBool('IOInvert', False)

    def get_camera_properties(self):
        """Return a dict mapping the property names to a dict with keys:
        (andor_type, read_only, units, range_hint), where andor_type is one of
        'Int', 'String', 'Bool', 'Float', or 'Enum'; read_only is a boolean;
        units is None or the name of the relevant units; and range_hint is None
        or a hint as to the data range."""
        properties = {}
        for py_name, prop in self._CAMERA_PROPERTIES.items():
            andor_type = prop['at_type']
            read_only = prop['readonly']
            units = self._UNITS.get(py_name)
            properties[py_name] = dict(andor_type=andor_type, read_only=read_only, units=units)
        properties['live_mode'] = dict(andor_type='Bool', read_only=False, units=None)
        return properties

    def get_basic_properties(self):
        return self._BASIC_PROPERTIES

    def _maybe_update_frame_rate_and_range(self, at_feature):
        """When setting a property, the frame rate range may change. If so,
        update the range and set the frame rate to the max possible."""
        if at_feature in self._PROPERTIES_THAT_CAN_CHANGE_FRAME_RATE_RANGE:
            min, max = self.get_frame_rate_range()
            self._update_property('frame_rate_range', (min, max))
            if lowlevel.IsWritable('FrameRate'):
                lowlevel.SetFloat('FrameRate', max)
                self._update_property('frame_rate', max)

    # STATE-STACK HANDLING
    # there are complex dependencies here. When pushing, better to set frame_count AFTER cycle_mode,
    # and trigger_mode AFTER exposure_time, and overlap_enabled after all the things it depends on.
    # when popping, better to go in reverse order from setting the dependent parameters like overlap and frame_count.
    # Also, always better to set frame_rate last, because many things can change the available range.
    # In all cases, want to turn off live mode ASAP or turn it on at the end
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
            live_weight = 2  # turn on last
        else:
            live_weight = -4 # turn off first
        weights['live_mode'] = live_weight
        return weights

    def _update_push_states(self, state, old_state):
        keys_to_deduplicate = set(state.keys())
        if 'trigger_mode' in keys_to_deduplicate and old_state['trigger_mode'] != state['trigger_mode']:
            # if we're changing the trigger mode, the overlap mode may change automatically,
            # so we don't want to assume that the old_state value is authoritative.
            if 'overlap_enabled' in keys_to_deduplicate:
                keys_to_deduplicate.remove('overlap_enabled')
        for k in keys_to_deduplicate:
            if old_state[k] == state[k]:
                state.pop(k)
                old_state.pop(k)

        if state.get('overlap_enabled', False):
            # Setting overlap_enabled can clobber the exposure time,
            # so we need to make sure to save the existing exposure time.
            old_state['exposure_time'] = self.get_exposure_time()

    def get_readout_time(self):
        """Return sensor readout time in ms"""
        return 1000 * lowlevel.GetFloat('ReadoutTime')

    def get_overlap_enabled(self):
        """Return whether overlap mode is enabled"""
        try:
            return lowlevel.GetBool('Overlap')
        except lowlevel.AndorError:
            return None

    def set_overlap_enabled(self, enabled):
        """Enable or disable overlap mode."""
        if self.get_shutter_mode() == 'Rolling' and self.get_trigger_mode() == 'Software' and enabled is False:
            # Setting overlap mode in software trigger / rolling shutter is an error,
            # but trying to unset it in this mode should not be...
            return
        lowlevel.SetBool('Overlap', enabled)
        self._maybe_update_frame_rate_and_range('Overlap')

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
            lowlevel.SetEnumString(self._set_sensor_gain_feature, value)
            lowlevel.SetEnumString('PixelEncoding', self._GAIN_TO_ENCODING[value])

    def get_aoi(self):
        """Convenience wrapper around the aoi_left, aoi_top, aoi_width, aoi_height
        properties. When setting this property, None elements and omitted entries
        cause the corresponding aoi_* property to be left unmodified."""
        return {
            'aoi_left': self.get_aoi_left(),
            'aoi_top': self.get_aoi_top(),
            'aoi_width': self.get_aoi_width(),
            'aoi_height': self.get_aoi_height()
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
        # TODO: calculate for Sona; this is Zyla-specific
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
        """Get the latest image that the camera retrieved, its timestamp, and
        its frame number."""
        # Return the name of the shared memory buffer that the latest live image
        # was stored in. The scope_client code will transparently retrieve the
        # image bytes based on this name, either via the ISM_Buffer mechanism if
        # the client is on the same machine, or over the network.
        if self._latest_data is None:
            raise RuntimeError('No image has been acquired.')
        # note: this function (and ONLY this function in this file) can get called
        # simultaneously from two threads. Below operations need to be atomic,
        # intrinsically thread-safe, or serialized.
        name, array, frame_number, timestamp = self._latest_data
        transfer_ism_buffer.register_array_for_transfer(name, array)
        return name, timestamp, frame_number

    def _update_image_data(self, name, array, timestamp):
        """Update information about the latest image, and broadcast to the world
        that another image has been retrieved."""
        self._frame_number += 1
        self._latest_data = name, array, self._frame_number, timestamp
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
        self.push_state(cycle_mode='Continuous', trigger_mode='Software')
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
        with self.image_sequence_acquisition(frame_count=1, **camera_params):
            read_timeout_ms = self.get_exposure_time() + 1000 # exposure time + 1 second
            return self.next_image(read_timeout_ms)

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
        self.push_state(live_mode=False) # turn off live mode first so that when we push the rest of the state, we don't get state parameters that are valid only for live mode
        self.push_state(cycle_mode=cycle_mode, trigger_mode=trigger_mode, **camera_params)
        lowlevel.Flush()
        self._buffer_maker = BufferFactory(namebase, frame_count=frame_count, cycle=False)
        if frame_count is not None:
            # if we have a known number of images to acquire, create and queue buffers for them now.
            # however, don't queue up more than a gig or so of images
            max_queue = int(1024**3 / self.get_image_byte_count())
            for i in range(min(max_queue, frame_count)):
                self._buffer_maker.queue_buffer()
        lowlevel.Command('AcquisitionStart')

    def next_image_and_metadata(self, read_timeout_ms=None):
        """Retrieve the next image from the image acquisition sequence. Will block
        if the image has not yet been triggered or retrieved from the camera.
        If a timeout is provided, either an image will be returned within that time
        or an AndorError of TIMEDOUT will be raised. If the timeout is None,
        then the call will block until an image becomes available.

        Returns the image, timestamp, and frame number.
        """
        if read_timeout_ms is None:
            read_timeout_ms = lowlevel.ANDOR_INFINITE
        else:
            read_timeout_ms = int(round(read_timeout_ms))
        self._buffer_maker.queue_if_needed()
        lowlevel.WaitBuffer(read_timeout_ms)
        self._update_image_data(*self._buffer_maker.convert_buffer())
        return self.latest_image()

    def next_image(self, read_timeout_ms=None):
        """Retrieve the next image from the image acquisition sequence. Will block
        if the image has not yet been triggered or retrieved from the camera.
        If a timeout is provided, either an image will be returned within that time
        or an AndorError of TIMEDOUT will be raised. If the timeout is None,
        then the call will block until an image becomes available.

        Returns only the image, discarding the timestamp and frame number.
        """
        return self.next_image_and_metadata(read_timeout_ms)[0] # return just the ism_buffer name

    def end_image_sequence_acquisition(self):
        """Stop an image-acquisition sequence and perform necessary cleanup."""
        lowlevel.Command('AcquisitionStop')
        lowlevel.Flush()
        self.pop_state() # need to pop twice because we pushed twice in start_image_sequence_acquisition() (see above)
        self.pop_state()
        del self._buffer_maker

    @contextlib.contextmanager
    def image_sequence_acquisition(self, frame_count=1, trigger_mode='Internal', **camera_params):
        """Context manager to begin and automatically end an image sequence acquisition."""
        self.start_image_sequence_acquisition(frame_count, trigger_mode, **camera_params)
        try:
            yield
        finally:
            self.end_image_sequence_acquisition()

    def flush():
        """Flush the camera RAM, which can be used to recover from a bad state."""
        lowlevel.Flush()

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
           overlap is whether overlap mode must be enabled or disabled to allow the requested frame rate

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
            if self.get_shutter_mode() == 'Global' and 1/desired_frame_rate > self.readout_time():
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
        image_names = []
        timestamps = []
        with self.image_sequence_acquisition(frame_count, frame_rate=frame_rate,
                trigger_mode='Internal', overlap_enabled=overlap, **camera_params):
            read_time = 1/min(self.get_max_interface_fps(), frame_rate)
            for _ in range(frame_count):
                name, timestamp, frame = self.next_image_and_metadata(3 * read_time * 1000)
                image_names.append(name)
                timestamps.append(timestamp)
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
        output_array = transfer_ism_buffer.create_array(name, shape=self.buffer_shape,
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
        except:
            logger.log_exception('Camera live mode thread crashed:')
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
        self.timeout = 250 + int(1000 * trigger_interval) * 3 # convert to ms and triple plus add 250 ms for safety margin

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
            if e.args[0].startswith('TIMEDOUT'):
                self.timeout_count += 1
                if self.timeout_count > 10:
                    raise lowlevel.AndorError('Live image retrieval timing out.')
                return
            else:
                raise
        self.update()
        self.image_count += 1
        self.latest_intervals.append(time.time() - t)

