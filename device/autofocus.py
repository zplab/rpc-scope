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
# Authors: Zach Pincus, Erik Hvatum

from misc import image_fft
import numpy
import time
from ..util import transfer_ism_buffer

def brenner(array, z):
    x_diffs = (array[2:, :] - array[:-2, :])**2
    y_diffs = (array[:, 2:] - array[:, :-2])**2
    return x_diffs.sum() + y_diffs.sum()

_high_pass_filter = None
def high_pass_brenner(array, z):
    global _high_pass_filter
    if _high_pass_filter is None or _high_pass_filter.shape != array.shape:
        _high_pass_filter = image_fft.highpass_butterworth_nd(1/5, array.shape, 1, 2)
        _high_pass_filter[0,0] = 0
    hp_filtered = image_fft.filter_nd(array, _high_pass_filter).real
    return brenner(hp_filtered, z)

METRICS = {'brenner': brenner,
           'high pass + brenner' : high_pass_brenner}

class Autofocus:
    def __init__(self, camera, stage):
        self._camera = camera
        self._stage = stage

    def autofocus(self, start, end, steps, metric='high pass + brenner'):
        """Move the stage stepwise from start to end, taking an image at
        each step. Apply the given autofocus metric and move to the best-focused
        position."""
        metric = METRICS[metric]
        exp_time = self._camera.get_exposure_time()
        self._camera.start_image_sequence_acquisition(steps, trigger_mode='Software', pixel_readout_rate='280 MHz')
        focus_metrics = []
        with self._stage._pushed_state(async=True):
            z_positions = numpy.linspace(start, end, steps)
            self._stage.set_z(start)
            for next_step in range(1, steps+1): # step through with index of NEXT step. Will make sense when you read below
#               t = time.time()
                self._stage.wait()
#               print(time.time() - t)
                self._camera.send_software_trigger()
                # if there is a next z position, wait for the exposure to finish and
                # get the stage moving there
                if next_step < steps:
                    time.sleep(exp_time / 1000) # exp_time is in ms, sleep is in sec
                    self._stage.set_z(z_positions[next_step])
                name = self._camera.next_image(read_timeout_ms=exp_time+1000)
                array = transfer_ism_buffer._release_array(name)
                focus_metrics.append(metric(array, z_positions[next_step-1]))
            self._camera.end_image_sequence_acquisition()
            focus_order = numpy.argsort(focus_metrics)
            best_z = z_positions[focus_order[-1]]
            self._stage.set_z(best_z) # go to focal plane with highest score
            self._stage.wait()
            return best_z, list(zip(z_positions, focus_metrics))

    def autofocus_continuous_move(self, start, end, speed, metric='brenner', fps_max=None):
        """Move the stage from 'start' to 'end' at a constant speed, taking images
        for autofocus constantly. If fps_max is None, take images as fast as
        possible; otherwise take images as governed by fps_max. Apply the autofocus
        metric to each image and move to the best-focused position."""
        metric = METRICS[metric]
        exp_time_sec = self._camera.get_exposure_time() * 1000
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
        with self._stage._pushed_state(async=True, z_speed=speed):
            self._stage.wait()
            z_positions = []
            self._stage.set_z(end)
            while self._stage.has_pending(): # while stage-move event is still in progress
                self._camera.send_software_trigger()
                # just queue the images up on the camera head while we do this
                z_positions.append(self._stage.get_z())
                time.sleep(sleep_time)
        self._stage.wait() # make sure all events are cleared out
        focus_metrics = []
        for z in z_positions:
            name = self._camera.next_image(read_timeout_ms=1000)
            array = transfer_ism_buffer._release_array(name)
            focus_metrics.append(metric(array, z))
        # now that we've retrieved all the images, end the acquisition
        self._camera.end_image_sequence_acquisition()
        focus_order = numpy.argsort(focus_metrics)
        best_z = z_positions(focus_order[-1])
        self._stage.set_z(best_z) # go to focal plane with highest score
        self._stage.wait() # no op if in sync mode, necessary in async mode
        return best_z, zip(z_positions, focus_metrics)

