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
import queue
import functools
import os.path

from zplib.image import fast_fft
from ..util import transfer_ism_buffer

FFTW_WISDOM = os.path.expanduser('~/fftw_wisdom')
if os.path.exists(FFTW_WISDOM):
    fast_fft.load_plan_hints(FFTW_WISDOM)

class AutofocusMetric:
    def __init__(self, shape):
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
        t0 = time.time()
        self.filter = fast_fft.SpatialFilter(shape, self.PERIOD_RANGE, precision=32, threads=8, better_plan=True)
        if time.time() - t0 > 0.5:
            fast_fft.store_plan_hints(FFTW_WISDOM)

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
def get_metric(metric, shape):
    return METRICS[metric](shape)

class Autofocus:
    def __init__(self, camera, stage):
        self._camera = camera
        self._stage = stage

    def _start_autofocus(self, metric):
        self._metric = get_metric(self._camera.get_aoi_shape())
        self._camera.start_image_sequence_acquisition(steps, trigger_mode='Software', pixel_readout_rate='280 MHz')

    def _stop_autofocus(self, z_positions):
        self._camera.end_image_sequence_acquisition()
        best_i, z_scores = self._metric.find_best_focus_index()
        best_z = z_positions[best_i]
        del self._metric
        self._stage.set_z(best_z) # go to focal plane with highest score
        self._stage.wait() # no op if in sync mode, necessary in async mode
        return best_z, zip(z_positions, z_scores)

    def autofocus(self, start, end, steps, metric='high pass + brenner'):
        """Move the stage stepwise from start to end, taking an image at
        each step. Apply the given autofocus metric and move to the best-focused
        position."""
        exp_time = self._camera.get_exposure_time()
        z_positions = numpy.linspace(start, end, steps)
        self._start_autofocus(metric)
        runner = MetricRunner(self._camera, self._metric)
        with self._stage._pushed_state(async=False):
            for z in z_positions:
                self._stage.set_z(z)
                self._camera.send_software_trigger()
                runner.add_image()
                # if there is a next exposure, wait for the exposure to finish
                if z != end:
                    time.sleep(exp_time / 1000) # exp_time is in ms, sleep is in sec
        image_names, camera_timestamps = runner.stop()
        best_z, positions_and_scores = self._stop_autofocus(z_positions)
        return best_z, positions_and_scores, image_names

    def autofocus_continuous_move(self, start, end, steps=None, speed=0.2, metric='brenner'):
        """Move the stage from 'start' to 'end' at a constant speed, taking images
        for autofocus constantly. If num_images is None, take images as fast as
        possible; otherwise take approximately the spcified number. If more images
        are requested than can be obtained, images will be taken as fast as possible
        and fewer images than requested will be returned.

        Once the images are obtained, this function applies the autofocus metric
        to each image and moves to the best-focused position."""
        trigger_interval = self._camera._calculate_live_trigger_interval()
        if steps is None:
            sleep_time = trigger_interval
        else:
            distance = abs(end - start)
            with self._stage._pushed_state(z_speed=speed):
                movement_time = self._stage.calculate_movement_time(distance)
            requested_fps = (steps - 1) / movement_time # subtract 1 to account for fencepost problem
            sleep_time = max(1/requested_fps, trigger_interval)

        with self._stage._pushed_state(async=True, z_speed=speed):
            self._stage.set_z(start) # move to start position
            # while that's going on, set up some things
            self._start_autofocus(metric)
            runner = MetricRunner(self._camera, self._metric)
            zrecorder = ZRecorder(self._camera, self._stage)
            self._stage.wait() # wait for stage to get to start position
            zrecorder.start()
            self._stage.set_z(end)
            while self._stage.has_pending(): # while stage-move event is still in progress
                self._camera.send_software_trigger()
                runner.add_image()
                time.sleep(sleep_time)
        self._stage.wait() # make sure all events are cleared out
        zrecorder.stop()
        image_names, camera_timestamps = runner.stop()
        z_positions = zrecorder.interpolate_zs(camera_timestamps)
        best_z, positions_and_scores = self._stop_autofocus(z_positions)
        return best_z, positions_and_scores, image_names

class MetricRunner(threading.Thread):
    def __init__(self, camera, metric):
        self.camera = camera
        self.metric = metric
        # we don't actually queue any information other than that there is a job to be done
        # but the Queue semantics are perfect for this anyway. Otherwise we'd need a lock
        # and a counter, which Queue nicely encapsulates.
        self.job_queue = queue.Queue()
        self.camera_timestamps = []
        self.image_names = []
        super().__init__()
        self.start()

    def add_image(self):
        self.job_queue.put(None)

    def stop(self):
        self.job_queue.join() # wait until enough task_done() calls are made to match the number of put() calls
        self.running = False
        self.join()
        return self.image_names, self.camera_timestamps

    def run(self):
        self.running = True
        while self.running:
            try:
                self.job_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            name = self.camera.next_image(read_timeout_ms=1000)
            self.image_names.append(name)
            self.camera_timestamps.append(self.camera.get_latest_timestamp())
            array = transfer_ism_buffer._borrow_array(name)
            self.metric.evaluate_image(array)
            self.job_queue.task_done()

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
        self.ts += self.ct0 # now ts is

    def interpolate_zs(self, camera_timestamps):
        return numpy.interp(camera_timestamps, self.ts, self.zs)

    def run(self):
        self.running = True
        while self.running:
            self.zs.append(self.stage.get_z())
            self.ts.append(time.time())
            time.sleep(self.sleep_time)
