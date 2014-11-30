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
# Authors: Zach Pincus

import numpy
from . import ism_buffer_utils

def brenner(array, z):
    x_diffs = (array[2:, :] - array[:-2, :])**2
    y_diffs = (array[:, 2:] - array[:, :-2])**2
    return x_diffs.sum() + y_diffs.sum()

METRICS = {'brenner': brenner}

class Autofocus:
    def __init__(self, camera, stage):
        self._camera = camera
        self._stage = stage

    def autofocus(self, start, end, steps, metric='brenner'):
        metric = METRICS[metric]
        read_timeout_ms = self._camera.get_exposure_time()
        self._camera.start_image_sequence_acquisition(steps, trigger_mode='Software', pixel_readout_rate='280 MHz')
        focus_values = []
        async = self._stage.get_async()
        self._stage.set_async(False)
        for z in numpy.linspace(start, end, steps):
            self._stage.set_z(z)
            self._camera.send_software_trigger()
            name = self._camera.next_image(read_timeout_ms)
            array = ism_buffer_utils._release_array(name)
            focus_values.append((metric(array, z), z))
        self._camera.end_image_sequence_acquisition()
        focus_values.sort()
        self._stage.set_z(focus_values[-1][1]) # go to focal plane with highest score
        self._stage.set_async(async)