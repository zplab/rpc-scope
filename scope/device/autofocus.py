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

from wautofocuser import wautofocuser
import numpy
import time
import scipy.signal as signal
from concurrent import futures
import threading
import queue

from ..util import transfer_ism_buffer

def brenner(array):
    x_diffs = (array[2:, :] - array[:-2, :])**2
    y_diffs = (array[:, 2:] - array[:, :-2])**2
    return x_diffs.sum() + y_diffs.sum()

_high_pass_filter = None
def high_pass_brenner(array):
    global _high_pass_filter
    if _high_pass_filter is None or array.shape != (_high_pass_filter.w, _high_pass_filter.h):
        _high_pass_filter = wautofocuser.SpatialFilter(array.shape[0], array.shape[1], 10)
    filtered_array = _high_pass_filter(array.astype(numpy.float32) / 65535)
    return brenner(filtered_array)

_band_pass_filter = None
def band_pass_brenner(array):
    global _band_pass_filter
    if _band_pass_filter is None or array.shape != (_band_pass_filter.w, _band_pass_filter.h):
        _band_pass_filter = wautofocuser.SpatialFilter(array.shape[0], array.shape[1], 60, 100)
    filtered_array = _band_pass_filter(array.astype(numpy.float32) / 65535)
    return brenner(filtered_array)

def multi_brenner(array):
    return high_pass_brenner(array), band_pass_brenner(array)

# first parameter is order of the filter, second is the critical frequency as a fraction of nyquist
# since the nyquist frequency is 2x the sampling rate, 2/n gives the frequency in terms of n spatial samples
B, A = signal.butter(2, 2/40, 'highpass')

def high_pass_brenner_lfilter(array):
    filtered_x = signal.lfilter(B, A, array, axis=0)
    filtered_y = signal.lfilter(B, A, array, axis=1)
    x_diffs = (filtered_x[2:, :] - filtered_x[:-2, :])**2
    y_diffs = (filtered_y[:, 2:] - filtered_y[:, :-2])**2
    return x_diffs.sum() + y_diffs.sum()


METRICS = {
    'brenner': brenner,
    'high pass + brenner' : high_pass_brenner,
    'lfilter high pass + brenner': high_pass_brenner_lfilter,
    'band pass + brenner' : band_pass_brenner,
    'multi-brenner': multi_brenner
}

def simple_focus_chooser(focus_metrics, z_positions):
    best_z = z_positions[numpy.argmax(focus_metrics)]
    return best_z, focus_metrics

def multi_brenner_focus_chooser(focus_metrics, z_positions):
    hp_metrics, bp_metrics = numpy.transpose(focus_metrics, dtype=numpy.float32)
    hp_metrics /= hp_metrics.max()
    bp_metrics /= bp_metrics.max()
    focus_metrics = hp_metrics * bp_metrics
    return simple_focus_chooser(focus_metrics, z_positions)

FOCUS_CHOOSERS = {
    'brenner': simple_focus_chooser,
    'high pass + brenner' : simple_focus_chooser,
    'lfilter high pass + brenner': simple_focus_chooser,
    'band pass + brenner' : simple_focus_chooser,
    'multi-brenner': multi_brenner_focus_chooser
}

class Autofocus:
    def __init__(self, camera, stage):
        self._camera = camera
        self._stage = stage

    def autofocus(self, start, end, steps, metric='high pass + brenner'):
        """Move the stage stepwise from start to end, taking an image at
        each step. Apply the given autofocus metric and move to the best-focused
        position."""
        focus_chooser = FOCUS_CHOOSERS[metric]
        metric = METRICS[metric]

        exp_time = self._camera.get_exposure_time()
        self._camera.start_image_sequence_acquisition(steps, trigger_mode='Software', pixel_readout_rate='280 MHz')
        focus_metrics = []
        image_names = []
        with self._stage._pushed_state(async=True):
            z_positions = numpy.linspace(start, end, steps)
            self._stage.set_z(start)
            for next_step in range(1, steps+1): # step through with index of NEXT step. Will make sense when you read below
                self._stage.wait()
                self._camera.send_software_trigger()
                # if there is a next z position, wait for the exposure to finish and
                # get the stage moving there
                if next_step < steps:
                    time.sleep(exp_time / 1000) # exp_time is in ms, sleep is in sec
                    self._stage.set_z(z_positions[next_step])
                name = self._camera.next_image(read_timeout_ms=exp_time+1000)
                array = transfer_ism_buffer._borrow_array(name)
                image_names.append(name)
                focus_metrics.append(metric(array))
            self._camera.end_image_sequence_acquisition()
            best_z, z_scores = focus_chooser(focus_metrics, z_positions)
            self._stage.set_z(best_z) # go to focal plane with highest score
            self._stage.wait()
            return best_z, zip(z_positions, z_scores), image_names

    def old_autofocus_continuous_move(self, start, end, speed, metric='brenner', fps_max=None, ims=None, max_workers=1):
        """Move the stage from 'start' to 'end' at a constant speed, taking images
        for autofocus constantly. If fps_max is None, take images as fast as
        possible; otherwise take images as governed by fps_max. Apply the autofocus
        metric to each image and move to the best-focused position."""
        metric = METRICS[metric]
        exp_time_sec = self._camera.get_exposure_time() / 1000
        if fps_max is None:
            sleep_time = exp_time_sec
        else:
            sleep_time = max(1/fps_max, exp_time_sec)
        # ideal case: would use camera internal triggering, and use exposure events
        # to read off the z-position at each acquisition start. But we don't have
        # that as of Dec 2014, so we fake it with software triggers.
        self._camera.start_image_sequence_acquisition(frame_count=None, trigger_mode='Software', pixel_readout_rate='280 MHz')
        # move the stage to the start position BEFORE we slow down the speed
        self._stage.set_z(start)
        self._stage.wait() # no op if in sync mode, necessary in async mode
        evaluator = ImageEvaluator(self._camera, metric, ims, max_workers)
        with self._stage._pushed_state(async=True, z_speed=speed):
            self._stage.wait()
            self._stage.set_z(end)
            while self._stage.has_pending(): # while stage-move event is still in progress
                self._camera.send_software_trigger()
                # just queue the images up on the camera head while we do this
                evaluator.z_queue.put(self._stage.get_z())
                time.sleep(sleep_time)
        self._stage.wait() # make sure all events are cleared out
        z_values, focus_metrics = evaluator.get_focus_values()
        # now that we've retrieved all the images, end the acquisition
        self._camera.end_image_sequence_acquisition()
        focus_order = numpy.argsort(focus_metrics)
        best_z = z_values[focus_order[-1]]
        self._stage.set_z(best_z) # go to focal plane with highest score
        self._stage.wait() # no op if in sync mode, necessary in async mode
        return best_z, zip(z_values, focus_metrics)

    def autofocus_continuous_move(self, start, end, speed, metric='brenner', num_images=None):
        """Move the stage from 'start' to 'end' at a constant speed, taking images
        for autofocus constantly. If num_images is None, take images as fast as
        possible; otherwise take approximately the spcified number. If more images
        are requested than can be obtained, images will be taken as fast as possible
        and fewer images than requested will be returned.

        Once the images are obtained, this function applies the autofocus metric
        to each image and moves to the best-focused position."""
        focus_chooser = FOCUS_CHOOSERS[metric]
        metric = METRICS[metric]

        self._camera.start_image_sequence_acquisition(frame_count=None, trigger_mode='Software', pixel_readout_rate='280 MHz')
        trigger_interval = self._camera._calculate_live_trigger_interval()
        if num_images is None:
            sleep_time = trigger_interval
        else:
            distance = abs(end - start)
            with self._stage._pushed_state(z_speed=speed):
                movement_time = self._stage.calculate_movement_time(distance)
            requested_fps = num_images / movement_time
            sleep_time = max(1/requested_fps, trigger_interval)

        self._stage.set_z(start)
        self._stage.wait() # no op if in sync mode, necessary in async mode
        evaluator = NewImageEvaluator(self._camera, metric)
        zrecorder = ZRecorder(self._camera, self._stage)
        with self._stage._pushed_state(async=True, z_speed=speed):
            self._stage.set_z(end)
            while self._stage.has_pending(): # while stage-move event is still in progress
                self._camera.send_software_trigger()
                # just queue the images up on the camera head while we do this
                evaluator.add_image()
                time.sleep(sleep_time)
        self._stage.wait() # make sure all events are cleared out
        zrecorder.stop()
        image_names, camera_timestamps, focus_metrics = evaluator.evaluate()
        # now that we've retrieved all the images, end the acquisition
        self._camera.end_image_sequence_acquisition()
        z_positions = zrecorder.interpolate_zs(camera_timestamps)
        best_z, z_scores = focus_chooser(focus_metrics, z_positions)
        self._stage.set_z(best_z) # go to focal plane with highest score
        self._stage.wait() # no op if in sync mode, necessary in async mode
        return best_z, zip(z_positions, z_scores), image_names

class ZRecorder(threading.Thread):
    def __init__(self, camera, stage, sleep_time=0.01):
        self.stage = stage
        self.sleep_time = sleep_time
        self.ts = []
        self.zs = []
        self.ct_hz = camera.get_timestamp_hz()
        self.ct0 = camera.get_current_timestamp()
        self.t0 = time.time()
        self.done = threading.Event()
        super().__init__()
        self.start()

    def stop(self):
        self.running = False
        self.done.wait()
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
        self.done.set()


class ImageEvaluator(threading.Thread):
    def __init__(self, camera, metric, ims, max_workers=1):
        self.camera = camera
        self.metric = metric
        self.ims = ims
        self.z_queue = queue.Queue()
        self.executor = futures.ThreadPoolExecutor(max_workers)
        self.running = True
        self.focus_futures = []
        self.z_values = []
        super().__init__()
        self.start()

    def timer(self, array, z):
        value = self.metric(array)
        return value

    def get_focus_values(self):
        self.z_queue.join() # wait until enough task_done() calls are made to match the number of put() calls
        self.running = False
        self.join()
        focus_metrics = [fut.result() for fut in self.focus_futures]
        self.executor.shutdown()
        return self.z_values, focus_metrics

    def run(self):
        while self.running:
            try:
                z_value = self.z_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            self.z_values.append(z_value)
            name = self.camera.next_image(read_timeout_ms=1000)
            array = transfer_ism_buffer._release_array(name)
            if self.ims is not None:
                self.ims.append(array)
            self.focus_futures.append(self.executor.submit(self.timer, array, z_value))
            self.z_queue.task_done()


class NewImageEvaluator(threading.Thread):
    def __init__(self, camera, metric):
        self.camera = camera
        self.metric = metric
        # we don't actually queue any information other than that there is a job to be done
        # but the Queue semantics are perfect for this anyway.
        self.job_queue = queue.Queue()
        self.focus_metrics = []
        self.camera_timestamps = []
        self.image_names = []
        super().__init__()
        self.start()

    def add_image(self):
        self.job_queue.put(None)

    def evaluate(self):
        self.job_queue.join() # wait until enough task_done() calls are made to match the number of put() calls
        self.running = False
        self.join()
        return self.image_names, self.camera_timestamps, self.focus_metrics

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
            self.focus_metrics.append(self.metric(array))
            self.job_queue.task_done()