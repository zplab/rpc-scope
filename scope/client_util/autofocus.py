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

    Returns: coarse_result, fine_result
        where each result is a triplet of (best_z, positions_and_scores, images),
        where best_z is the position of the best focus, positions_and_scores is
        a list of (z_position, focus_score) pairs, and images is a list
        of images for each focal plane (return_images=True) or an empty list.
    """
    coarse_result = autofocus(scope, z_start, z_max, coarse_range_mm, coarse_steps,
        speed=0.8, binning='4x4', exposure_time=scope.camera.exposure_time/16, return_images=return_images)
    fine_result = autofocus(scope, coarse_result[0], z_max, fine_range_mm, fine_steps,
        speed=0.3, binning='1x1', return_images=return_images)
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

    Returns: best_z, positions_and_scores, images
        where best_z is the position of the best focus, positions_and_scores is
        a list of (z_position, focus_score) pairs, and images is a list
        of images for each focal plane (return_images=True) or an empty list.
    """
    offset = range_mm / 2
    start = z_start - offset
    end = min(z_start + offset, z_max)
    # run ensure_fft_ready (which has a long timeout) to make sure that the FFT filters
    # have been computed before we actually do an autofocus.
    scope.camera.autofocus.ensure_fft_ready()
    best_z, positions_and_scores, images = scope.camera.autofocus.autofocus_continuous_move(start, end,
        steps=steps, max_speed=speed, focus_filter_mask=mask, return_images=return_images, **camera_params)
    return best_z, positions_and_scores, images