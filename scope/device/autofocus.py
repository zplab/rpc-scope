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
# Authors: Zach Pincus, Erik Hvatum

import numpy
import time
from concurrent import futures
import threading
import functools

from zplib.image import fast_fft
from ..util import transfer_ism_buffer
from ..util import logging
from ..config import scope_configuration

logger = logging.get_logger(__name__)

FFTW_WISDOM = scope_configuration.CONFIG_DIR / 'fftw_wisdom'
if FFTW_WISDOM.exists():
    fast_fft.load_plan_hints(str(FFTW_WISDOM))
    logger.debug('FFTW wisdom loaded')
else:
    logger.warning('no FFTW wisdom found!')

class AutofocusMetric:
    def __init__(self, shape):
        self.reset()

    def reset(self):
        self.focus_scores = []

    def evaluate_image(self, image):
        self.focus_scores.append(self.metric(image))

    def metric(self, image):
        raise NotImplementedError()

    def find_best_focus_index(self):
        best_i = numpy.argmax(self.focus_scores)
        focus_scores = self.focus_scores
        self.focus_scores = []
        return best_i, focus_scores

class Brenner(AutofocusMetric):
    @staticmethod
    def metric(image):
        image = image.astype(numpy.float32) # otherwise can get overflow in the squaring and summation
        x_diffs = (image[2:, :] - image[:-2, :])**2
        y_diffs = (image[:, 2:] - image[:, :-2])**2
        return x_diffs.sum() + y_diffs.sum()

class FilteredBrenner(Brenner):
    def __init__(self, shape):
        super().__init__(shape)
        timer = threading.Timer(1, logger.warning, ['Slow construction of FFTW filter detected, presumably because no cached plan could be found. May take >30 minutes!'])
        timer.start()
        self.filter = fast_fft.SpatialFilter(shape, self.PERIOD_RANGE, precision=32, threads=6, better_plan=True)
        if timer.is_alive():
            timer.cancel()
        else: # timer went off and warning was issued...
            logger.info('FFT filter constructed. Caching plan wisdom for next time.')
            fast_fft.store_plan_hints(str(FFTW_WISDOM))

    def metric(self, image):
        filtered = self.filter.filter(image)
        return super().metric(filtered)

class HighpassBrenner(FilteredBrenner):
    PERIOD_RANGE = (None, 10)

class BandpassBrenner(FilteredBrenner):
    PERIOD_RANGE = (60, 100)

class MultiBrenner(AutofocusMetric):
    def __init__(self, shape):
        super().__init__(shape)
        self.hp = HighpassBrenner(shape)
        self.bp = BandpassBrenner(shape)

    def metric(self, image):
        return hp.metric(image), lp.metric(image)

    def find_best_focus_index(self):
        hp_scores, bp_scores = numpy.transpose(self.focus_scores, dtype=numpy.float32)
        hp_scores /= hp_scores.max()
        bp_scores /= bp_scores.max()
        self.focus_scores = hp_scores * bp_scores
        return super().find_best_focus_index()


METRICS = {
    'brenner': Brenner,
    'high pass + brenner' : HighpassBrenner,
    'band pass + brenner' : BandpassBrenner,
    'multi-brenner': MultiBrenner
}

@functools.lru_cache(maxsize=16)
def _get_metric(metric, shape):
    return METRICS[metric](shape)

def get_metric(metric, shape):
    metric = _get_metric(metric, shape) # return a possibly-cached version
    metric.reset() # make sure the metric state is reset so we don't get a partially-used metric.
    return metric

class Autofocus:
    _CAMERA_MODE = dict(readout_rate='280 MHz', shutter_mode='Rolling')

    def __init__(self, camera, stage):
        self._camera = camera
        self._stage = stage

    def _start_autofocus(self, metric, **camera_state):
        camera_state.update(self._CAMERA_MODE)
        self._camera.push_state(**camera_state)
        self._metric = get_metric(metric, self._camera.get_aoi_shape())

    def _stop_autofocus(self, z_positions):
        self._camera.pop_state()
        best_i, z_scores = self._metric.find_best_focus_index()
        best_z = z_positions[best_i]
        del self._metric
        self._stage.set_z(best_z) # go to focal plane with highest score
        self._stage.wait() # no op if in sync mode, necessary in async mode
        return best_z, zip(z_positions, z_scores)

    def autofocus(self, start, end, steps, metric='high pass + brenner',
            return_images=False, **camera_state):
        """Move the stage stepwise from start to end, taking an image at
        each step. Apply the given autofocus metric and move to the best-focused
        position."""
        self._start_autofocus(metric, **camera_state)
        frame_rate, overlap = self._camera.calculate_streaming_mode(steps, trigger_mode='Software', desired_frame_rate=1000) # try to get the max possible frame rate...
        self._camera.start_image_sequence_acquisition(frame_count=steps, trigger_mode='Software')
        z_positions = numpy.linspace(start, end, steps)
        runner = MetricRunner(self._camera, frame_rate, steps, self._metric, return_images)
        runner.start()
        for z in z_positions:
            self._stage.set_z(z)
            self._stage.wait()
            self._camera.send_software_trigger()
            if z != end:
                time.sleep(sleep_time)
        image_names, camera_timestamps = runner.join()
        self._camera.end_image_sequence_acquisition()
        best_z, positions_and_scores = self._stop_autofocus(z_positions)
        if return_images:
            return best_z, positions_and_scores, image_names
        else:
            return best_z, positions_and_scores

    def autofocus_continuous_move(self, start, end, steps=None, max_speed=0.2,
            metric='high pass + brenner', return_images=False, **camera_state):
        """Move the stage from 'start' to 'end' at a constant speed, taking images
        for autofocus constantly. If num_images is None, take images as fast as
        possible; otherwise take approximately the specified number. If more images
        are requested than can be obtained for a given stage speed, the stage will
        move more slowly.

        Once the images are obtained, this function applies the autofocus metric
        to each image and moves to the best-focused position."""
        self._start_autofocus(metric, **camera_state)
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
        with self._stage.in_state(async=False, z_speed=speed):
            zrecorder.start()
            self._camera.start_image_sequence_acquisition(frame_count=steps, trigger_mode='Internal',
              frame_rate=frame_rate, overlap_enabled=overlap)
            runner.start()
            self._stage.set_z(end)
        zrecorder.stop()
        image_names, camera_timestamps = runner.join()
        self._camera.end_image_sequence_acquisition()
        if len(camera_timestamps) != steps:
            self._camera.pop_state()
            raise RuntimeError('Autofocus image acquisition failed: Expected {} images, got {}.'.format(steps, len(camera_timestamps)))
        z_positions = zrecorder.interpolate_zs(camera_timestamps)
        best_z, positions_and_scores = self._stop_autofocus(z_positions)
        if return_images:
            return best_z, positions_and_scores, image_names
        else:
            return best_z, positions_and_scores

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
                name = self.camera.next_image(self.read_timeout_ms)
                self.camera_timestamps.append(self.camera.get_latest_timestamp())
                if self.retain_images:
                    self.image_names.append(name)
                    array = transfer_ism_buffer._borrow_array(name)
                else:
                    array = transfer_ism_buffer._release_array(name)
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
