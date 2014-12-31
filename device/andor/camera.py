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
import atexit
import itertools

from . import lowlevel
from ...util import transfer_ism_buffer
from ...util import enumerated_properties
from ...util import property_device
from ... import scope_configuration as config

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
        ('MetadataEnable', lowlevel.SetBool, True),
        ('MetadataTimestamp', lowlevel.SetBool, True),
        ('TriggerMode', lowlevel.SetEnumString, 'Internal'), # need to set internal trigger mode to be able to set overlap
        ('Overlap', lowlevel.SetBool, False),
        ('PixelReadoutRate', lowlevel.SetEnumString, '100 MHz'),
        ('SensorCooling', lowlevel.SetBool, True),
        ('SimplePreAmpGainControl', lowlevel.SetEnumString, '16-bit (low noise & high well capacity)'),
        ('SpuriousNoiseFilter', lowlevel.SetBool, True),
        ('StaticBlemishCorrection', lowlevel.SetBool, True),
        ('TriggerMode', lowlevel.SetEnumString, 'Software'), # now back to software triggering
#        ('VerticallyCenterAOI', lowlevel.SetBool, False)
    ]

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
        self._encoding_enum = self._add_andor_enum('PixelEncoding', 'pixel_encoding', readonly=True)
        self._add_andor_enum('PixelReadoutRate', 'pixel_readout_rate')
        self._gain_enum = self._add_andor_enum('SimplePreAmpGainControl', 'sensor_gain', custom_setter=True) # setter defined below uses _gain_enum
        self._add_andor_enum('ElectronicShutteringMode', 'shutter_mode')
        self._add_andor_enum('TriggerMode', 'trigger_mode')
        # TODO: figure out why TemperatureStatus never updates with a callback...
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
        self._add_andor_property('ReadoutTime', 'readout_time', 'Float', readonly=True)
        self._add_andor_property('SerialNumber', 'serial_number', 'String', readonly=True)
        self._add_andor_property('SpuriousNoiseFilter', 'spurious_noise_filter_enabled', 'Bool')
        self._add_andor_property('StaticBlemishCorrection', 'static_blemish_correction_enabled', 'Bool')
        self._add_andor_property('TimestampClock', 'current_timestamp', 'Int', readonly=True)
        self._add_andor_property('TimestampClockFrequency', 'timestamp_ticks_per_second', 'Int', readonly=True)
        self._add_andor_property('SensorCooling', 'sensor_cooling_enabled', 'Bool', readonly=True)
        self._add_andor_property('SensorTemperature', 'sensor_temperature', 'Float', readonly=True)

        # define custom getter and setters for exposure_time below
        self._add_property_data('ExposureTime', 'Float', False, 'exposure_time', self.get_exposure_time)


        if property_server:
            self._c_callback = lowlevel.FeatureCallback(self._andor_callback)
            for at_feature in self._callback_properties.keys():
                lowlevel.RegisterFeatureCallback(at_feature, self._c_callback, 0)

        self._update_live_frame = self._add_property('live_frame', None)
        self._update_property('live_mode', False)
        self._latest_live_array = None
        self._state_stack = []

    def return_to_default_state(self):
        """Set the camera to its default, baseline state. Always a good idea to do before doing anything else."""
        with self._live_guarded():
            if lowlevel.GetBool('CameraAcquiring'):
                lowlevel.Command('AcquisitionStop')
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

        if not readonly and not custom_setter:
            def setter(value):
                with self._live_guarded():
                    enum.set_value(value)
            setattr(self, 'set_'+py_name, setter)
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
                with self._live_guarded():
                    andor_setter(at_feature, value)
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

    @contextlib.contextmanager
    def _live_guarded(self):
        """context manager to pause and resume live mode around a with-block
        in which live imaging can't be allowed (e.g. during acquisition of another image.)"""
        live = self._live_mode
        if live:
            self.set_live_mode(False)
        try:
            yield
        finally:
            if live:
                self.set_live_mode(True)


    def set_state(self, **state):
        """Set a number of camera parameters at once using keyword arguments, e.g.
        camera.set_state(exposure_time=50, frame_rate=10)"""
        for k, v in state.items():
            getattr(self, 'set_'+k)(v)

    def push_state(self, **state):
        """Set a number of camera parameters at once using keyword arguments, while
        saving the old values of those parameters. pop_state() will restore those
        previous values. push_state/pop_state pairs can be nested arbitrarily."""
        old_state = {k: getattr(self, 'get_'+k)() for k in state.keys()}
        self._state_stack.append(old_state)
        overlap = state.pop('overlap_enabled', None)
        self.set_state(**state)
        # overlap mode has complex dependencies, so it generally shouldn't be set until the very end
        # when presumably those dependencies are satisfied
        if overlap is not None and lowlevel.IsWritable('Overlap'):
            self.set_overlap_enabled(overlap)

    def pop_state(self):
        """Restore the most recent set of camera parameters changed by a push_state()
        call."""
        old_state = self._state_stack.pop()
        overlap = old_state.pop('overlap_enabled', None)
        # overlap mode has complex dependencies, so it generally should be unset first, before
        # other changes make overlap mode no longer writable
        if overlap is not None and lowlevel.IsWritable('Overlap'):
            self.set_overlap_enabled(overlap)
        self.set_state(**old_state)

    @contextlib.contextmanager
    def _pushed_state(self, **state):
        """context manager to push and pop state around a with-block"""
        self.push_state(**state)
        try:
            yield
        finally:
            self.pop_state()

    def get_exposure_time(self):
        """Return exposure time in ms"""
        return 1000 * lowlevel.GetFloat('ExposureTime')

    def set_exposure_time(self, ms):
        """Set the exposure time in ms. If necessary, live imaging will be paused."""
        sec = ms / 1000
        live = self._live_mode
        if live: # pause live if we can't do fast exposure switching
            current_exposure = lowlevel.GetFloat('ExposureTime')
            read_time = self.get_readout_time()
            current_short = current_exposure < read_time
            new_short = sec < read_time
            must_pause_live = current_short != new_short
            if must_pause_live:
                self.set_live_mode(False)
        lowlevel.SetFloat('ExposureTime', sec)
        if live:
            if must_pause_live:
                self.set_live_mode(True)
            else:
                # changed exposure time without pausing live... update sleep time
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
        with self._live_guarded:
            self._gain_enum.set_value(value)
            if value.startswith('12'):
                # make sure we always use the packed encoding for 12-bit mode
                lowlevel.SetEnumIndex('PixelEncoding', self._encoding_enum._usr_to_hw['Mono12Packed'])

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
        # are valid together. However, if aoi_left is greater than 2061 before the change, aoi_left
        # must be updated before aoi_width.
        #
        # Performing AOI updates in ascending order of signed parameter value change ensures that setting
        # a collection of AOI parameters that are together legal does not require transitioning through
        # an illegal state.
        aoi_list = [(key, value) for key, value in aoi_dict.items() if value is not None]
        for key, value in sorted(aoi_list, key = self._delta_sort_key):
            with self._live_guarded():
                getattr(self, 'set_' + key)(value)

    def full_aoi(self):
        """Set the AOI to full frame"""
        self._set_aoi({'aoi_height': 2160, 'aoi_left': 1, 'aoi_top': 1, 'aoi_width': 2560})

    def get_live_mode(self):
        return self._live_mode

    def set_live_mode(self, enabled):
        if enabled:
            self._enable_live()
        else:
            self._disable_live()
        self._update_property('live_mode', enabled)

    def live_image(self):
        """Get the latest live image from the camera."""
        # Return the name of the shared memory buffer that the latest live image
        # was stored in. The scope_client code will transparently retrieve the
        # image bytes based on this name, either via the ISM_Buffer mechanism if
        # the client is on the same machine, or over the network.
        name, array = self._latest_live_array
        transfer_ism_buffer.server_register_array_for_transfer(name, array)
        return name

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
        self.push_state(overlap_enabled=False, cycle_mode='Continuous', trigger_mode='Software', pixel_readout_rate='280 MHz')
        trigger_interval = self._calculate_live_trigger_interval()
        namebase = 'live@-'+str(time.time())
        buffer_maker = BufferFactory(namebase, frame_count=1, cycle=True)
        self._live_mode = True
        lowlevel.Command('AcquisitionStart')
        def update(frame_number):
            self._latest_live_array = buffer_maker.convert_buffer()
            self._update_live_frame(frame_number)
        self._live_reader = LiveReader(buffer_maker.queue_buffer, update, trigger_interval)
        self._live_trigger = LiveTrigger(trigger_interval, self._live_reader)

    def _calculate_live_trigger_interval(self):
        """Determine how long to wait between sending acquisition triggers in
        live mode, based on data from the andor API and also knowledge from the
        camera manual about how many cycles things take in different camera modes.
        Returns trigger interval in seconds."""
        readout_time = self.get_readout_time()
        if self.get_exposure_time() / 1000 <= readout_time:
            # It may be a bug in the andor library that get_frame_rate() is wrong
            # for short exposures (< readout_time), but in any case, it is, so we
            # need to note that software triggering mode (used for live viewing)
            # takes two full read cycles per image.
            frame_time = readout_time * 2
        else:
            frame_time = 1/self.get_frame_rate()
        trigger_interval = max(1/self.get_max_interface_fps(), frame_time) * 1.05
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
        self._update_live_frame(None)
        # Note: do not set self._live_buffer_name or self._live_array to None.
        # Instead let them stick around, so if any clients wanted to call live_image()
        # to obtain the live array, they can still grab the last frame.
        # This avoids the race condition where live mode is turned off right before
        # a client tries to grab the image.
        self.pop_state()

    def get_live_fps(self):
        if not self._live_mode:
            return
        if not self._live_reader.latest_intervals:
            # no intervals yet
            return 0
        return 1/numpy.mean(self._live_reader.latest_intervals)

    def acquire_image(self):
        """Acquire a single image from the camera, with its current settings.
        NB: This is a SLOW way to acquire multiple images. In that case,
        use the start_image_sequence_acquisition(), next_image(), and
        end_image_sequence_acquisition() functions, with software/internal/external
        triggering as appropriate."""
        read_timeout_ms = self.get_exposure_time() + 1000 # exposure time + 1 second
        self.start_image_sequence_acquisition(frame_count=1)
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

        After starting an image sequence, next_image() can be called to retrieve
        images from the camera, and after all images have been received,
        end_image_sequence_acquisition() will properly clean up the acquisition
        state.

        """
        if hasattr(self, '_sequence_acquisition_state'):
            raise RuntimeError('Already acquiring an image sequence.')
        if frame_count == 1:
            namebase = 'acquire@'+str(time.time())
        else:
            namebase = 'sequence@{}-'.format(time.time())
        if frame_count is None:
            cycle_mode = 'Continuous'
        else:
            cycle_mode = 'Fixed'
            camera_params['frame_count'] = frame_count
        self._live_before_sequence_acquisition = self._live_mode
        self.set_live_mode(False)
        lowlevel.Flush()
        self.push_state(cycle_mode=cycle_mode, trigger_mode=trigger_mode, **camera_params)
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
        name, output_array = self._buffer_maker.convert_buffer()
        transfer_ism_buffer.server_register_array_for_transfer(name, output_array)
        # Return the name of the shared memory buffer that the image
        # was stored in. The scope_client code will transparently retrieve the
        # image bytes based on this name, either via the ISM_Buffer mechanism if
        # the client is on the same machine, or over the network.
        return name

    def end_image_sequence_acquisition(self):
        """Stop an image-acquisition sequence and perform necessary cleanup."""
        lowlevel.Command('AcquisitionStop')
        lowlevel.Flush()
        self.pop_state()
        self.set_live_mode(self._live_before_sequence_acquisition)
        del self._buffer_maker


UINT8_P = ctypes.POINTER(ctypes.c_uint8)

class BufferFactory:
    def __init__(self, namebase, frame_count=1, cycle=False):
        width, height, stride = map(lowlevel.GetInt, ('AOIWidth', 'AOIHeight', 'AOIStride'))
        self.buffer_shape = (width, height)
        input_encoding = lowlevel.GetEnumStringByIndex('PixelEncoding', lowlevel.GetEnumIndex('PixelEncoding'))
        self.convert_buffer_args = (width, height, stride, input_encoding, 'Mono16')
        image_buffer_ctype = ctypes.c_uint8 * lowlevel.GetInt('ImageSizeBytes')
        self.queued_buffers = collections.deque()
        if cycle:
            self.buffers = itertools.cycle([image_buffer_ctype() for i in range(frame_count)])
        else:
            self.buffers = self._new_buffer_iter(image_buffer_ctype, frame_count)
        if frame_count == 1 and not cycle:
            self.names = iter([namebase])
        else:
            self.names = self._name_iter(namebase)

    def _new_buffer_iter(self, image_buffer_ctype, frame_count):
        i = 0
        while True:
            i += 1
            yield image_buffer_ctype()
            if frame_count is not None and i == frame_count:
                return

    def _name_iter(self, namebase):
        i = 0
        while True:
            yield namebase + str(i)
            i += 1

    def queue_buffer(self):
        buf = next(self.buffers)
        lowlevel.QueueBuffer(buf, len(buf))
        self.queued_buffers.append(buf)

    def queue_if_needed(self):
        if not self.queued_buffers:
            self.queue_buffer()

    def convert_buffer(self):
        name = next(self.names)
        output_array = transfer_ism_buffer.server_create_array(name, shape=self.buffer_shape,
            dtype=numpy.uint16, order='Fortran')
        lowlevel.ConvertBuffer(self.queued_buffers.popleft(), output_array.ctypes.data_as(UINT8_P),
            *self.convert_buffer_args)
        return name, output_array

class SequenceAcquisitionState:
    def __init__(self, live, names, output_arrays, convert_buffers):
        self.live = live
        self.acquire_data = zip(names, output_arrays, convert_buffers)

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
        update(image_count) which (presumably) will deal with the buffer
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
        self.update(self.image_count)
        self.image_count += 1
        self.latest_intervals.append(time.time() - t)

