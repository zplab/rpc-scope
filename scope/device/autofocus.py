# This code is licensed under the MIT License (see LICENSE file for details)

import numpy
import time
from concurrent import futures
import threading
import functools
import runpy

import freeimage
from zplib.image import fast_fft

from ..util import transfer_ism_buffer
from ..util import logging
from ..config import scope_configuration
from . import andor
from .leica import stage

logger = logging.get_logger(__name__)

FFTW_WISDOM = scope_configuration.CONFIG_DIR / 'fftw_wisdom'
if FFTW_WISDOM.exists():
    loaded = fast_fft.load_plan_hints(str(FFTW_WISDOM))
    if loaded:
        logger.debug('FFTW wisdom loaded')
    else:
        logger.warning('FFTW wisdom file exists, but some wisdom could not be loaded (FFTW version mismatch?)')
else:
    logger.warning('No FFTW wisdom found!')

@functools.lru_cache(maxsize=16)
def _get_filter(shape, period_range):
    timer = threading.Timer(1, logger.warning, ['Slow construction of FFTW filter for image shape {} (likely no cached plan could be found). May take >30 minutes!', shape])
    timer.start()
    fft_filter = fast_fft.SpatialFilter(shape, period_range, precision=32, threads=6, better_plan=True)
    if timer.is_alive():
        timer.cancel()
    else: # timer went off and warning was issued...
        logger.info('FFT filter constructed. Caching plan wisdom for next time.')
        fast_fft.store_plan_hints(str(FFTW_WISDOM))
    return fft_filter.filter


class AutofocusMetricBase:
    def __init__(self, shape, mask=None, fft_period_range=None):
        if mask is not None:
            assert mask.shape == shape
        self.mask = mask
        if fft_period_range is None:
            self.filter = None
        else:
            self.filter = _get_filter(tuple(shape), tuple(fft_period_range))
        self.focus_scores = []

    def evaluate_image(self, image):
        if self.filter is not None:
            image = self.filter(image)
        self.focus_scores.append(self.metric(image, self.mask))

    def metric(self, image, mask):
        raise NotImplementedError()

    def find_best_focus_index(self):
        best_i = numpy.argmax(self.focus_scores)
        focus_scores = self.focus_scores
        return best_i, focus_scores

class AutofocusMetric(AutofocusMetricBase):
    def __init__(self, metric, shape, mask=None, fft_period_range=None, **metric_kws):
        super().__init__(shape, mask, fft_period_range)
        self._metric = metric
        self.metric_kws = metric_kws

    def metric(self, image, mask):
        return self._metric(image, mask, **self.metric_kws)

def brenner_metric(image, mask):
    image = image.astype(numpy.float32) # otherwise can get overflow in the squaring and summation
    x_diffs = (image[2:, :] - image[:-2, :])**2
    y_diffs = (image[:, 2:] - image[:, :-2])**2
    if mask is None:
        return x_diffs.sum() + y_diffs.sum()
    else:
        return x_diffs[mask[1:-1, :]].sum() + y_diffs[mask[:, 1:-1]].sum()

_METRICS = dict(brenner=brenner_metric)

def get_metric(metric, shape, mask, fft_period_range, **kws):
    if isinstance(metric, str):
        if metric in _METRICS:
            metric = _METRICS[metric]
        elif ':' in metric:
            path, metric = metric.split(':')
            metric = runpy.run_path(path)[metric]
        else:
            raise ValueError('"metric" must be the name of a known metric or formatted as "/path/to/file.py:function"')
    assert callable(metric)
    if issubclass(metric, AutofocusMetricBase):
        return metric(shape, mask, fft_period_range, **kws)
    else:
        return AutofocusMetric(metric, shape, mask, fft_period_range, **kws)

class Autofocus:
    _CAMERA_DEFAULTS = dict(readout_rate='280 MHz', shutter_mode='Rolling')

    def __init__(self, camera: andor.Camera, stage: stage.Stage):
        self._camera = camera
        self._stage = stage

    def ensure_fft_ready(self):
        """Make sure the autofocus FFT filter is ready for the current camera
        frame size. (No need to worry about the metric_filter_period_range: the
        FFT doesn't need to know that to compute the basic filter.)

        The first time that this is done after installing / updating fftw,
        this might take a while. So this function is available separetely so
        that it can be run with a very long timeout.
        """
        # use a dummy period range below
        _get_filter(shape=tuple(self._camera.get_aoi_shape()), period_range=(None, 2))

    def _enter_camera_state(self, **camera_state):
        final_state = dict(self._CAMERA_DEFAULTS)
        final_state.update(camera_state)
        self._camera.push_state(**final_state)

    def _start_autofocus(self, metric='brenner', metric_kws=None, metric_mask=None,
            metric_filter_period_range=None, **camera_state):
        self._enter_camera_state(**camera_state)
        if isinstance(metric_mask, str):
            metric_mask = freeimage.read(metric_mask) > 0
        shape = self._camera.get_aoi_shape()
        self._metric = get_metric(metric, shape, metric_mask, metric_filter_period_range, **metric_kws)

    def _stop_autofocus(self, z_positions):
        self._camera.pop_state()
        best_i, z_scores = self._metric.find_best_focus_index()
        best_z = z_positions[best_i]
        del self._metric
        self._stage.set_z(best_z) # go to focal plane with highest score
        self._stage.wait() # no op if in sync mode, necessary in async mode
        return best_z, zip(z_positions, z_scores)

    def autofocus(self, start, end, steps, metric='brenner', metric_kws=None,
            metric_mask=None, metric_filter_period_range=None,
            return_images=False, **camera_state):
        """Automatically focus the camera with stepwise stage movements.

        This moves the stage stepwise from start to end, taking an image at
        each step. The Brenner autofocus metric is applied to each image,
        and then the stage is moved to the best-focused position.

        Parameters:
            start, end: z-positions of focus bounds (inclusive)
            steps: number of focal planes to sample between start and end.
            metric: autofocus metric to use. Can be either:
                1) A function to be called as metric(image, mask, **metric_kws)
                    which will return a focus score (high is good).
                2) A subclass of AutofocusMetricBase, which will be instantiated
                    as metric(shape, mask, metric_filter_period_range, **metric_kws),
                    and will be used to evaluate images and find the best one.
                3) The string name of a known metric function or subclass. Currently
                    'brenner' is supported.
                4) A string of the form "/path/to/file.py:object" where object
                    is the name of either a function or subclass to be called
                    as in 1 or 2.
                Note: When using the scope server, only options 3 and 4 are
                available.
            metric_kws: keyword arguments for metric function or class, as above.
            metric_mask: file path to a mask image with nonzero values at
                regions of the image where the focus should be evaluated.
            metric_filter_period_range: if None, the image will not be filtered.
                Otherwise, this must be a tuple of (min_size, max_size),
                representing the minimum and maximum spatial size of objects in
                the image that will remain after filtering.
            return_images: if True, the images obtained will be returned.
            **camera_state: additional state information for the camera during
                autofocus.

        Returns: best_z, positions_and_scores, images
            best_z: z position of best focus
            positions_and_scores: list of (z, focus_score) tuples.
            images: if return_images is True, a list of images acquired, otherwise
                an empty list.
        """
        self._start_autofocus(metric, metric_kws, metric_mask, metric_filter_period_range, **camera_state)
        frame_rate, overlap = self._camera.calculate_streaming_mode(steps, trigger_mode='Software', desired_frame_rate=1000) # try to get the max possible frame rate...
        z_positions = numpy.linspace(start, end, steps)
        runner = MetricRunner(self._camera, frame_rate, steps, self._metric, return_images)
        with self._camera.image_sequence_acquisition(steps, trigger_mode='Software'):
            runner.start()
            for z in z_positions:
                self._stage.set_z(z)
                self._stage.wait()
                self._camera.send_software_trigger()
                if z != end:
                    time.sleep(1/frame_rate)
            image_names, camera_timestamps = runner.join()
        best_z, positions_and_scores = self._stop_autofocus(z_positions)
        if not return_images:
            image_names = []
        return best_z, positions_and_scores, image_names

    def autofocus_continuous_move(self, start, end, steps=None, max_speed=0.2,
            metric='brenner', metric_kws=None, metric_mask=None, metric_filter_period_range=None,
            return_images=False, **camera_state):
        """Automatically focus the camera with continuous stage movements.

        This moves the stage continuously from start to end, taking images
        throughout. The Brenner autofocus metric is applied to each image,
        and then the stage is moved to the best-focused position.

        Parameters:
            start, end: z-positions of focus bounds (inclusive)
            steps: approximate number of focal planes to sample between start
                and end. If None, images will be acquired as fast as possible.
            max_speed: z-speed at which to move the stage (mm/s). If more steps
                are requested than the camera can obtain at this speed, the
                stage speed will be slower.
            metric: autofocus metric to use. Can be either:
                1) A function to be called as metric(image, mask, **metric_kws)
                    which will return a focus score (high is good).
                2) A subclass of AutofocusMetricBase, which will be instantiated
                    as metric(shape, mask, metric_filter_period_range, **metric_kws),
                    and will be used to evaluate images and find the best one.
                3) The string name of a known metric function or subclass. Currently
                    'brenner' is supported.
                4) A string of the form "/path/to/file.py:object" where object
                    is the name of either a function or subclass to be called
                    as in 1 or 2.
                Note: When using the scope server, only options 3 and 4 are
                available.
            metric_kws: keyword arguments for metric function or class, as above.
            metric_mask: file path to a mask image with nonzero values at
                regions of the image where the focus should be evaluated.
            metric_filter_period_range: if None, the image will not be filtered.
                Otherwise, this must be a tuple of (min_size, max_size),
                representing the minimum and maximum spatial size of objects in
                the image that will remain after filtering.
            return_images: if True, the images obtained will be returned.
            **camera_state: additional state information for the camera during
                autofocus.

        Returns: best_z, positions_and_scores, images
            best_z: z position of best focus
            positions_and_scores: list of (z, focus_score) tuples.
            images: if return_images is True, a list of images acquired, otherwise
                an empty list
        """
        self._start_autofocus(metric, metric_kws, metric_mask, metric_filter_period_range, **camera_state)
        distance = abs(end - start)
        with self._stage.in_state(z_speed=max_speed):
            min_movement_time = self._stage.calculate_z_movement_time(distance)
        if steps is None:
            speed = max_speed
            with self._camera.in_state(live_mode=False, overlap_enabled=True, trigger_mode='Internal'):
                min_overlap_frame_rate, max_overlap_frame_rate = self._camera.get_frame_rate_range()
            steps = int(numpy.ceil(min_movement_time * max_overlap_frame_rate)) # overlap is fastest mode...
            if steps <= self._camera.get_safe_image_count_to_queue():
                frame_rate = max_overlap_frame_rate
                overlap = True
            else:
                # back off on the frame rate to sustainable streaming rate
                frame_rate = self._camera.get_max_interface_fps()
                steps = int(numpy.ceil(min_movement_time * frame_rate))
                overlap = frame_rate >= min_overlap_frame_rate
        else:
            desired_frame_rate = steps / min_movement_time
            frame_rate, overlap = self._camera.calculate_streaming_mode(steps, desired_frame_rate, trigger_mode='Internal')
            time_required = steps / frame_rate
            speed = self._stage.calculate_required_z_speed(distance, time_required)
        runner = MetricRunner(self._camera, frame_rate, steps, self._metric, return_images)
        zrecorder = ZRecorder(self._camera, self._stage)
        self._stage.set_z(start) # move to start position at original speed
        self._stage.wait()
        with self._camera.image_sequence_acquisition(steps, trigger_mode='Internal', frame_rate=frame_rate, overlap_enabled=overlap):
            zrecorder.start()
            runner.start()
            with self._stage.in_state(async=False, z_speed=speed):
                self._stage.set_z(end)
            zrecorder.stop()
            image_names, camera_timestamps = runner.join()
        if len(camera_timestamps) != steps:
            self._camera.pop_state()
            raise RuntimeError('Autofocus image acquisition failed: Expected {} images, got {}.'.format(steps, len(camera_timestamps)))
        z_positions = zrecorder.interpolate_zs(camera_timestamps)
        best_z, positions_and_scores = self._stop_autofocus(z_positions)
        if not return_images:
            image_names = []
        return best_z, positions_and_scores, image_names

class MetricRunner(threading.Thread):
    def __init__(self, camera, frame_rate, frame_count, metric, retain_images):
        self.camera = camera
        # need extra-long timeout because thread/CPU contention with autofocus eval somehow can slow down image retrieval (not a GIL issue!)
        self.read_timeout_ms = max(5000, 1/min(camera.get_max_interface_fps(), frame_rate) * 1000)
        self.frames_left = frame_count
        self.metric = metric
        self.camera_timestamps = []
        self.image_names = []
        self.retain_images = retain_images
        self.threadpool = futures.ThreadPoolExecutor(1)
        # want to run metrics in a single background thread:
        # fftw is already multithreaded so we let it handle that, and just run
        # it in a single thread to keep out of the way of retrieving images.
        self.futures = []
        super().__init__()

    def join(self):
        super().join()
        if self.exception:
            raise self.exception
        for future in self.futures:
            future.result() # make sure all metric evals are done, and raise errors if any of them did
        return self.image_names, self.camera_timestamps

    def run(self):
        try:
            self.exception = None
            while self.frames_left > 0:
                name, timestamp, frame = self.camera.next_image_and_metadata(self.read_timeout_ms)
                self.camera_timestamps.append(timestamp)
                if self.retain_images:
                    self.image_names.append(name)
                    array = transfer_ism_buffer.borrow_array(name)
                else:
                    array = transfer_ism_buffer.release_array(name)
                self.futures.append(self.threadpool.submit(self.metric.evaluate_image, array))
                self.frames_left -= 1
        except Exception as e:
            self.exception = e


class ZRecorder(threading.Thread):
    def __init__(self, camera, stage, sleep_time=0.01):
        super().__init__()
        self.stage = stage
        self.sleep_time = sleep_time
        self.ts = []
        self.zs = []
        self.ct_hz = camera.get_timestamp_hz()
        self.ct0 = camera.get_current_timestamp()
        self.t0 = time.time()

    def stop(self):
        self.running = False
        self.join()
        self.zs = numpy.array(self.zs)
        self.ts = numpy.array(self.ts)
        self.ts -= self.t0
        self.ts *= self.ct_hz # now ts is in camera-timestamp units
        self.ts += self.ct0 # now ts has same zero as the camera timestamp

    def interpolate_zs(self, camera_timestamps):
        return numpy.interp(camera_timestamps, self.ts, self.zs)

    def run(self):
        self.running = True
        while self.running:
            self.zs.append(self.stage.get_z())
            self.ts.append(time.time())
            time.sleep(self.sleep_time)
