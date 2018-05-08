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

    Returns: (coarse_z, coarse_images), (fine_z, fine_images)
        where coarse_z and fine_z are  the best z-position found at each
        autofocus stage, and coarse_images and fine_images are lists of the
        images returned, or empty lists if return_images=False.
    """
    exposure_time = scope.camera.exposure_time
    with scope.camera.in_state(readout_rate='280 MHz', shutter_mode='Rolling'), scope.stage.in_state(z_speed=1):
        coarse_z, coarse_images = autofocus(scope, z_start, z_max, coarse_range_mm, coarse_steps,
            speed=0.8, binning='4x4', exposure_time=exposure_time/16, return_images=return_images)
        fine_z, fine_images = autofocus(scope, coarse_z, z_max, fine_range_mm, fine_steps,
            speed=0.3, binning='1x1', return_images=return_images)
    return (coarse_z, coarse_images), (fine_z, fine_images)

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

    Returns: best_z, images
        where best_z is the position of the best focus, and images is a list
        of images for each focal plane (return_images=True) or an empty list.
    """
    offset = range_mm / 2
    start = z_start - offset
    end = min(z_start + offset, z_max)
    # set a 45-minute timeout to allow for FFT calculation if necessary
    with scope._rpc_client.timeout_sec(60*45):
        best_z, positions_and_scores, images = scope.camera.autofocus.autofocus_continuous_move(start, end,
            steps=steps, max_speed=speed, focus_filter_mask=mask, return_images=return_images, **camera_params)
        return best_z, images