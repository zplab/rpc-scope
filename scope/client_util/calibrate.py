# This code is licensed under the MIT License (see LICENSE file for details)

import contextlib
import time
import numpy
from scipy import ndimage

from zplib.scalar_stats import mcd

def image_order_statistic(image, k):
    return numpy.partition(image, k, axis=None)[k]

class DarkCurrentCorrector:
    """Class that acquires dark-current images and corrects newly-acquired images
    for the dark currents."""
    def __init__(self, scope, min_exposure_ms=0.5, max_exposure_ms=1000, frames_to_average=5):
        """Collect dark-current images across a range of exposures.

        NB: generally the dark-current images will only be valid for images
        acquired with identical camera parameters.

        Parameters:
            scope: scope client object
            min_exposure_ms, max_exposure_ms: exposure time range. Only images
                within this range can be corrected for their dark currents.
            frames_to_average: the given number of frames will be collected for
                each exposure step, reducing per-pixel noise effects.
        """
        requested_exposure_times = numpy.logspace(numpy.log10(min_exposure_ms), numpy.log10(max_exposure_ms), 10)
        self.dark_images = []
        self.exposure_times = []
        with contextlib.ExitStack() as stack:
            # set up all the scope states
            if hasattr(scope.il, 'shutter_open'):    # Inverted scope doesn't have shutters.
                stack.enter_context(scope.il.in_state(shutter_open=False))
                stack.enter_context(scope.tl.in_state(shutter_open=False))
            stack.enter_context(scope.tl.lamp.in_state(enabled=False))
            if hasattr(scope.il, 'spectra'):
                stack.enter_context(scope.il.spectra.in_state(**{lamp+'_enabled': False for lamp in scope.il.spectra.lamp_specs.keys()}))
            stack.enter_context(scope.camera.image_sequence_acquisition(len(requested_exposure_times)*frames_to_average, trigger_mode='Software'))

            for exp in requested_exposure_times:
                images = []
                scope.camera.exposure_time = exp
                # camera can only handle certain specific exposure times
                # so read out what it actually chose (generally within a few microseconds of requested
                # but might as well get it correct...)
                self.exposure_times.append(scope.camera.exposure_time)
                for i in range(frames_to_average):
                    scope.camera.send_software_trigger()
                    images.append(scope.camera.next_image(max(1000, 2*exp)))
                self.dark_images.append(numpy.mean(images, axis=0))

    def correct(self, image, exposure_ms):
        """Correct a given image for the dark-currents.

        Parameters:
            image: newly-acquired image from the camera
            exposure_ms: the exposure time for that image. NB: this MUST be the
                full length of time that the camera was exposing, even if the
                lights were on only for a portion of that duration (as with
                the acquisition_sequencer.)

        Returns: corrected image.
        """
        if exposure_ms < self.exposure_times[0] or exposure_ms > self.exposure_times[-1]:
            raise ValueError('Exposure time is outside of the calibration range')
        i = numpy.searchsorted(self.exposure_times, exposure_ms)
        if exposure_ms == self.exposure_times[i]:
            dark_image = self.dark_images[i]
        else:
            before_exp, after_exp = self.exposure_times[i-1], self.exposure_times[i]
            before_img, after_img = self.dark_images[i-1], self.dark_images[i]
            a = (exposure_ms - before_exp) / (after_exp - before_exp)
            dark_image = (1-a) * before_img + a * after_img
            dark_image.round()
            dark_image = dark_image.astype(numpy.uint16)
        int_image = image.astype(numpy.int32) - dark_image
        int_image[int_image < 0] = 0
        return int_image.astype(numpy.uint16)

def meter_exposure_and_intensity(scope, lamp, max_exposure=200, max_intensity=255,
    min_intensity_fraction=0.3, max_intensity_fraction=0.75):
    """Find an appropriate brightfield exposure setting.

    This function searches through lamp intensities and camera exposure times
    to find a combination where the brightfield image is neither overexposed nor
    under-exposed. Ideally this should be run on a sample region that will
    generate images as bright or brighter than any other region, so that
    the selected exposure time does not lead to overexposure on different sample
    regions.

    The camera and lamp will be left with the appropriate intensity and exposure
    settings.

    NB: generally the exposure time will only be valid for images acquired with
    identical camera parameters.

    Parameters:
        scope: scope client object
        lamp: lamp object to adjust (should be scope.camera.tl.lamp or one of
            the several lamps in scope.il.spectra)
        max_exposure: longest allowable exposure in ms
        max_intensity: largest allowable lamp intensity
        min_intensity_fraction: least bright value (in terms of the 90th
            percentile of image intensities) allowed for the image to count as
            'properly exposed', as a fraction of the camera bit depth.
            NB: if no other exposure times are valid and not over-exposed, an
            exposure time could be returned that yields images which fall below
            this minimum.
        max_intensity_fraction: brightest value (in terms of maximum image
            intensity, allowing for 25 hot pixels) allowed for the image to
            count as 'properly exposed', as a fraction of the camera bit depth.

    Returns: lamp_intensity, exposure_time, actual_bounds, requested_bounds
        lamp_intensity: lamp.intensity setting
        exposure_time: selected exposure time in ms
        actual_bounds: (min, max) tuple of intensities in the image
        requested_bounds: (min, max) tuple of requested bounds based on the
            intensity_fraction paramteters
    """
    intensities = numpy.linspace(255, 16, 18, dtype=numpy.uint8)
    intensities = intensities[intensities <= max_intensity]
    # First, find a decent lamp intensity setting: one where the pixels
    # are under the max allowed value, for a little above the minimum exposure time.
    # We don't use the bare minimum, because we want a value where the bare minimum
    # exposure has plenty of headroom (to allow for random noise, etc.)
    scope.camera.exposure_time = 3.5 # min exposure time is 2
    bit_depth = int(scope.camera.sensor_gain[:2])
    max_value = (2**bit_depth-1)
    max_good_value = max_intensity_fraction * max_value
    good_intensity = None
    with scope.camera.image_sequence_acquisition(len(intensities), trigger_mode='Software'), lamp.in_state(enabled=True):
        for intensity in intensities:
            lamp.intensity = intensity
            # We use an RC circuit to smooth out the PWM lamp-intensity signal
            # so we need to wait a little bit for the intensity to settle out
            time.sleep(0.25)
            scope.camera.send_software_trigger()
            image = scope.camera.next_image(1000)
            image_near_max, image_max = image_order_statistic(image, [-200, -10]) # allow 10 saturated pixels...
            if image_near_max < max_good_value and image_max < max_value:
                good_intensity = intensity
                break
    if good_intensity is None:
        if image_max == max_value:
            saturated = (image == max_value).sum()
            raise RuntimeError(f'Too many saturated pixels: at lowest brightness {saturated} pixels were at {max_value}, but only 10 are allowed.')
        else:
            raise RuntimeError(f'Could not find a non-overexposed lamp intensity: at lowest brightness, image near-max of {image_near_max} is >= cutoff of {max_good_value}.')
    # Now given the intensity setting, find the shortest-possible exposure time
    # that fully complies with the min and max requirements
    good_exposure, actual_bounds, requested_bounds = meter_exposure(scope, lamp, max_exposure, min_intensity_fraction, max_intensity_fraction)
    return good_intensity, good_exposure, actual_bounds, requested_bounds

def meter_exposure(scope, lamp, max_exposure=200, min_intensity_fraction=0.3,
    max_intensity_fraction=0.75):
    """Find an appropriate exposure setting.

    This function searches through camera exposure times to find the shortest
    possible exposure where the image is neither overexposed nor under-exposed.
    Ideally this should be run on a sample region that will generate images as
    bright or brighter than any other region, so that the selected exposure
    time does not lead to overexposure on different sample regions.

    The camera will be left with the appropriate exposure setting.

    NB: generally the exposure time will only be valid for images acquired with
    identical camera parameters.

    Parameters:
        scope: scope client object
        lamp: lamp object to adjust (should be scope.camera.tl.lamp or one of
            the several lamps in scope.il.spectra)
        max_exposure: longest allowable exposure in ms
        min_intensity_fraction: least bright value (in terms of the 90th
            percentile of image intensities) allowed for the image to count as
            'properly exposed', as a fraction of the camera bit depth.
            NB: if no other exposure times are valid and not over-exposed, an
            exposure time could be returned that yields images which fall below
            this minimum.
        max_intensity_fraction: brightest value (in terms of maximum image
            intensity) allowed for the image to count as 'properly exposed', as
            a fraction of the camera bit depth.

    Returns: exposure_time, actual_bounds, requested_bounds
        exposure_time: selected exposure time in ms
        actual_bounds: (min, max) tuple of intensities in the image
        requested_bounds: (min, max) tuple of requested bounds based on the
            intensity_fraction paramteters
    """
    # Exposure range is controlled by the curious property of the Zyla camera that
    # short exposures with bright lights yield really noisy images. Worse,
    # dark banding in the center can appear with exposures < 2 ms and too many
    # photons per second (which overwhelm the anti-bloom circuits, even outside
    # of the overexposed range).
    # So avoid exposures < 2 ms...
    # TODO: verify that this is still the case (last checked 2017)
    bit_depth = int(scope.camera.sensor_gain[:2])
    max_value = (2**bit_depth-1)
    min_good_value = min_intensity_fraction * max_value
    max_good_value = max_intensity_fraction * max_value
    # calculate exposure as int(2 * 1.25**i) for various i, rounded to the nearest 0.25
    max_i = (numpy.log(max_exposure)-numpy.log(4))/numpy.log(1.25)
    exposures = list((2 * 1.25**numpy.arange(int(max_i)) * 4).round()/4)
    if exposures[-1] < max_exposure:
        exposures.append(max_exposure)
    good_exposure = None
    with scope.camera.image_sequence_acquisition(len(exposures), trigger_mode='Software'), lamp.in_state(enabled=True):
        for exposure in exposures:
            scope.camera.exposure_time = exposure
            scope.camera.send_software_trigger()
            image = scope.camera.next_image(max(1000, 2*exposure))
            image_90th, image_near_max, image_max = image_order_statistic(image, [int(image.size * 0.90), -200, -10]) # allow 10 saturated pixels...
            if image_near_max < max_good_value and image_max < max_value:
                good_exposure = exposure
            else:
                break
            if image_90th > min_good_value:
                break
    if good_exposure is None:
        raise RuntimeError(f'Could not find a valid exposure time: intensity {lamp.intensity}, exposure {exposure}, image_90th {image_90th}, image_near_max {image_near_max}, image_max {image_max}, min_good {min_good_value}, max_good {max_good_value}')
    scope.camera.exposure_time = good_exposure
    return good_exposure, (image_90th, image_near_max), (min_good_value, max_good_value)

def get_vignette_mask(image, percent_vignetted=5):
    """Convert a well-exposed image (ideally a brightfield image with ~uniform
    intensity) into a mask delimiting the image region from the dark,
    vignetted borders of the image.

    percent_vignetted: percent (0-100) of pixels estimated to be in the vignetted region.
        35% is a good estimate for images with a full circular vignette
        (e.g. 0.7x optocoupler); 5% is reasonable for images with only small
        vignetted areas (e.g. 1x optocoupler).

    Returns: vignette_mask, which is True in the image regions.
    """
    bright_pixels = image[image > numpy.percentile(image[::4,::4], 1.5*percent_vignetted)]
    mean, std = mcd.robust_mean_std(bright_pixels[::10], 0.85)
    vignette_threshold = mean - 5 * std
    vignette_mask = image > vignette_threshold
    vignette_mask = ndimage.binary_closing(vignette_mask)
    vignette_mask = ndimage.binary_fill_holes(vignette_mask)
    vignette_mask = ndimage.binary_opening(vignette_mask, iterations=15)
    return vignette_mask

def get_averaged_images(scope, positions, dark_corrector, frames_to_average=5):
    """Obtain an averaged image across multiple stage positions and multiple
    exposures per position. The mean across exposures for each position is
    calculated, and the median across all the positions is returned.

    Parameters:
        scope: scope client object
        positions: list of (x,y,z) stage positions
        dark_corrector: DarkCurrentCorrector object
        frames_to_average: number of images to take at each position to average

    Returns: averaged image across frames and positions
    """
    position_images = []
    exposure_ms = scope.camera.exposure_time
    with scope.stage.in_state(async=False):
        for position in positions:
            scope.stage.position = position
            with scope.camera.image_sequence_acquisition(frames_to_average, trigger_mode='Internal'):
                images = [scope.camera.next_image() for i in range(frames_to_average)]
            images = [dark_corrector.correct(image, exposure_ms) for image in images]
            position_images.append(numpy.mean(images, axis=0))
    return numpy.median(position_images, axis=0)

def get_flat_field(image, vignette_mask):
    """Return a flat-field correction image.

    This function smooths out an image and corrects for vignetting to produce
    a "flat-field correction image" that can be used to correct uneven
    illumination.

    The input image should be well-exposed and without any visible features,
    and should be dark-current corrected. Ideally an averaged image using
    get_average_images() will be used.

    The returned correction image is used to correct an image as follows. First
    apply the dark-current correction and then multiply by the flat-field
    correction image. This yields an image with approximately the same overall
    mean intensity but corrected for illumination inhomogeneities.

    NB: Areas of the image that are determined to have been vignetted by the
    vignette_mask parameter will be set to zero in the flat-field image.

    Parameters:
        image: input image.
        vignette_mask: image mask that is True for regions that are NOT obscured
           by vignetting (the dark areas around the edge of the image).

    Returns: flat-field correction image and the median intensity of the non-
        vignetted image regions (after smoothing), for use as a measure of
        overall illumination intensity.
    """
    flat_field = numpy.array(image, dtype=float) # make a copy of the image because we modify it in-place
    near_vignette_mask = vignette_mask ^ ndimage.binary_erosion(vignette_mask, iterations=10)
    # set the vignetted region to a value that's the mean value of the pixels
    # nearest, so that when we do image smoothing those dark vignetted values
    # don't muck things up too much.
    flat_field[~vignette_mask] = flat_field[near_vignette_mask].mean()
    flat_field = _smooth_flat_field(flat_field)
    image_pixels = flat_field[vignette_mask]
    flat_field /= numpy.mean(image_pixels)
    flat_field[flat_field <= 0] = 1 # we're going to reciprocate, so prevent div/0 errors
    flat_field = 1 / flat_field # take reciprocal so that the mask can be used multiplicatively
    flat_field[~vignette_mask] = 0
    return flat_field, numpy.median(image_pixels)


def _circular_mask(s):
    xs, ys = numpy.indices((s, s)).astype(float) / (s-1)
    return (xs**2 + ys**2) <= 1

_m9 = _circular_mask(9)

def _smooth_flat_field(image):
    image = ndimage.gaussian_filter(image.astype(numpy.float32), 15, mode='nearest')
    image = image[::2, ::2]
    image = ndimage.median_filter(image, footprint=_m9)
    image = ndimage.zoom(image, 2)
    return ndimage.gaussian_filter(image, 5)
