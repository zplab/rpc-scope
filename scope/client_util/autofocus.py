# This code is licensed under the MIT License (see LICENSE file for details)

def coarse_fine_autofocus(scope, z_start, z_max, coarse_range_mm, coarse_steps,
    fine_range_mm, fine_steps, metric='brenner', metric_kws=None, metric_mask=None,
    metric_filter_period_range=None, return_images=False):
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
        metric: autofocus metric to use. Autofocus metrics can be either:
            1) A function to be called as metric(image, mask, **metric_kws)
                which will return a focus score (high is good).
            2) A subclass of AutofocusMetricBase, which will be instantiated
                as metric(shape, mask, metric_filter_period_range, **metric_kws),
                and will be used to evaluate images and find the best one.

            To specify such a function or subclass, this parameter can be either:
            1) The string name of a known metric function or subclass. Currently
                'brenner' is supported.
            2) A string of the form "/path/to/file.py:object" where object
                is the name of either a function or subclass to be called
                as above.
        metric_kws: keyword arguments for metric function or class, as above.
        metric_mask: file path to a mask image with nonzero values at
            regions of the image where the focus should be evaluated.
        metric_filter_period_range: if None, the image will not be filtered.
            Otherwise, this must be a tuple of (min_size, max_size),
            representing the minimum and maximum spatial size of objects in
            the image that will remain after filtering.
        return_images: if True, return the coarse and fine images acquired

    Returns: coarse_result, fine_result
        where each result is a triplet of (best_z, positions_and_scores, images),
        where best_z is the position of the best focus, positions_and_scores is
        a list of (z_position, focus_score) pairs, and images is a list
        of images for each focal plane (return_images=True) or an empty list.
    """
    with scope.camera.in_state(binning='4x4', exposure_time=scope.camera.exposure_time/16):
        coarse_result = autofocus(scope, z_start, z_max, coarse_range_mm, coarse_steps,
            speed=0.8, metric=metric, metric_kws=metric_kws, metric_mask=metric_mask,
            metric_filter_period_range=metric_filter_period_range, return_images=return_images)

    fine_result = autofocus(scope, coarse_result[0], z_max, fine_range_mm, fine_steps,
        speed=0.3, metric=metric, metric_kws=metric_kws, metric_mask=metric_mask,
        metric_filter_period_range=metric_filter_period_range, return_images=return_images)
    return coarse_result, fine_result

def autofocus(scope, z_start, z_max, range_mm, steps, speed=0.3,
    metric='brenner', metric_kws=None, metric_mask=None,
    metric_filter_period_range=None, return_images=False):
    """Run a single-pass autofocus.

    Parameters:
        scope: microscope client object.
        z_start: position to start autofocus from
        z_max: absolute max z-position to try (if going too high might crash the
            objective)
        range_mm: range to try to focus on, in mm around z_start
        steps: how many focus steps to take over the range
        speed: stage movement speed during autofocus in mm/s
        metric: autofocus metric to use. Autofocus metrics can be either:
            1) A function to be called as metric(image, mask, **metric_kws)
                which will return a focus score (high is good).
            2) A subclass of AutofocusMetricBase, which will be instantiated
                as metric(shape, mask, metric_filter_period_range, **metric_kws),
                and will be used to evaluate images and find the best one.

            To specify such a function or subclass, this parameter can be either:
            1) The string name of a known metric function or subclass. Currently
                'brenner' is supported.
            2) A string of the form "/path/to/file.py:object" where object
                is the name of either a function or subclass to be called
                as above.
        metric_kws: keyword arguments for metric function or class, as above.
        metric_mask: file path to a mask image with nonzero values at
            regions of the image where the focus should be evaluated.
        metric_filter_period_range: if None, the image will not be filtered.
            Otherwise, this must be a tuple of (min_size, max_size),
            representing the minimum and maximum spatial size of objects in
            the image that will remain after filtering.
        return_images: if True, return the coarse and fine images acquired

    Returns: best_z, positions_and_scores, images
        where best_z is the position of the best focus, positions_and_scores is
        a list of (z_position, focus_score) pairs, and images is a list
        of images for each focal plane (return_images=True) or an empty list.
    """
    offset = range_mm / 2
    start = z_start - offset
    end = min(z_start + offset, z_max)
    if metric_filter_period_range is not None:
        # run ensure_fft_ready (which has a long timeout) to make sure that the FFT filters
        # have been computed before we actually do an autofocus.
        scope.camera.autofocus.ensure_fft_ready()
    best_z, positions_and_scores, images = scope.camera.autofocus.autofocus_continuous_move(start, end,
        steps, speed, metric, metric_kws, metric_mask, metric_filter_period_range, return_images)
    return best_z, positions_and_scores, images