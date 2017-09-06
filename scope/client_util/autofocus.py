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


def coarse_fine_autofocus(scope, z_start, z_max, coarse_range_mm, coarse_steps, fine_range_mm, fine_steps, return_images=False):
    """Run a two-stage (coarse/fine) autofocus.

    Parameters:
        scope: microscope client object.
        z_start: position to start autofocus from
        z_max: absolute max z-position to try (if going too high might crash the
            objective)
        coarse_range_mm: range to try to focus on, in mm around z_start
        coarse_steps: how many focus steps to take over the coarse range
        fine_range_mm: range to try to focus on, in mm around the optimal coarse
            focal point
        fine_steps: how many focus steps to take over the fine range
        return_images: if True, return the coarse and fine images acquired

    Returns:
        If return_images is False, returns (coarse_z, fine_z) containing the
            best z-position found at each autofocus stage.
        If return_images is True, returns two pairs:
            (coarse_z, coarse_images), (fine_z, fine_images)
    """
    exposure_time = scope.camera.exposure_time
    with scope.camera.in_state(readout_rate='280 MHz', shutter_mode='Rolling'), scope.stage.in_state(z_speed=1):
        coarse_result = autofocus(scope, z_start, z_max, coarse_range_mm, coarse_steps, speed=0.8,
            binning='4x4', exposure_time=exposure_time/16, return_images=return_images)
        coarse_z = coarse_result[0] if return_images else coarse_result
        fine_result = autofocus(scope, coarse_z, z_max, fine_range_mm, fine_steps, speed=0.3,
            binning='1x1', return_images=return_images)
    return coarse_result, fine_result

def autofocus(scope, z_start, z_max, range_mm, steps, speed=0.3, return_images=False, mask=None, **camera_params):
    """Run a single-pass autofocus.

    Parameters:
        scope: microscope client object.
        z_start: position to start autofocus from
        z_max: absolute max z-position to try (if going too high might crash the
            objective)
        range_mm: range to try to focus on, in mm around z_start
        steps: how many focus steps to take over the range
        speed: stage movement speed during autofocus in mm/s
        return_images: if True, return the coarse and fine images acquired
        mask: filename of image mask defining region for autofocus to examine

    Returns:
        If return_images is False, return the best z-position.
        If return_images is True, returns the pair (z, images)
    """
    offset = range_mm / 2
    start = z_start - offset
    end = min(z_start + offset, z_max)
    # set a 45-minute timeout to allow for FFT calculation if necessary
    old_timeout = scope._rpc_client.timeout_sec
    scope._rpc_client.timeout_sec = 60 * 45
    try:
        values = scope.camera.autofocus.autofocus_continuous_move(start, end, steps=steps,
            max_speed=speed, focus_filter_mask=mask, return_images=return_images, **camera_params)
    finally:
        scope._rpc_client.timeout_sec = old_timeout
    if return_images:
        return values[0], values[2] # z-positions and images
    else:
        return values[0] # just z-positions