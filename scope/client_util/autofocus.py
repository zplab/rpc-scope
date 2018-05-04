# This code is licensed under the MIT License (see LICENSE file for details)

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
    with scope._rpc_client.timeout_sec(60*45):
        values = scope.camera.autofocus.autofocus_continuous_move(start, end, steps=steps,
            max_speed=speed, focus_filter_mask=mask, return_images=return_images, **camera_params)
    if return_images:
        return values[0], values[2] # z-positions and images
    else:
        return values[0] # just z-positions