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

from ..util import state_stack

def autofocus(scope, z_start, z_max, coarse_range_mm, coarse_steps, fine_range_mm, fine_steps):
    """Run a two-stage (coarse/fine) autofocus.

    Parameters:
        z_start: position to start autofocus from
        z_max: absolute max z-position to try (if going too high might crash the
            objective)
        coarse_range_mm: range to try to focus on, in mm around z_start
        coarse_steps: how many focus steps to take over the coarse range
        fine_range_mm: range to try to focus on, in mm around the optimal coarse
            focal point
        fine_steps: how many focus steps to take over the fine range

    Returns: coarse_z, fine_z: the z-positions found at each autofocus stage
    """
    exposure_time = scope.camera.exposure_time
    with state_stack.pushed_state(scope.tl.lamp, enabled=True):
        coarse_z = _autofocus(scope, z_start, z_max, coarse_range_mm, coarse_steps, speed=0.2,
            binning='4x4', exposure_time=exposure_time/16)
        fine_z = _autofocus(scope, coarse_z, z_max, fine_range_mm, fine_steps, speed=0.1,
            binning='1x1')
    return coarse_z, fine_z

def _autofocus(scope, z_start, z_max, range_mm, steps, speed, **camera_params):
    offset = range_mm / 2
    start = z_start - offset
    end = min(z_start + offset, z_max)
    with state_stack.pushed_state(scope.camera, **camera_params):
        focus_z, positions_and_scores = scope.camera.autofocus.autofocus_continuous_move(start, end,
            steps=steps, max_speed=speed, metric='high pass + brenner', return_images=False)
    return focus_z