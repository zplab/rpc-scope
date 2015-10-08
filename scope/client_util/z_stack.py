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
# Authors: Zach Pincus

import numpy
import time

def z_stack(scope, mm_range, num_steps):
    z = scope.stage.z
    z_positions = numpy.linspace(z - mm_range/2, z + mm_range/2, num_steps)
    scope.camera.start_image_sequence_acquisition(num_steps, trigger_mode='Software')
    images = []
    exposure_sec = scope.camera.exposure_time / 1000
    with scope.stage.in_state(async=True):
        # parallelize stage movement and image transfer by dispatching movement
        # and image-retrieval and then waiting for the stage to finish.
        # Overall this will run a bit faster than it would by doing everything
        # in strictly serial fashion.
        for z in z_positions:
            scope.stage.z = z
            if z != z_positions[0]:
                # don't do this for the first position -- no image to retrieve yet!
                images.append(scope.camera.next_image(read_timeout_ms=1000))
            scope.stage.wait()
            scope.camera.send_software_trigger()
            time.sleep(exposure_sec)
        images.append(scope.camera.next_image(read_timeout_ms=1000))
    scope.camera.end_image_sequence_acquisition()
    return images
