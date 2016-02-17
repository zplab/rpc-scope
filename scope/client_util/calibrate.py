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
        self.exposures = numpy.logspace(numpy.log10(min_exposure_ms), numpy.log10(max_exposure_ms), 10, base=10)
        self.dark_images = []
        with scope.il.in_state(shutter_open=False), \
             scope.tl.in_state(shutter_open=False), \
             scope.tl.lamp.in_state(enabled=False):
            if hasattr(scope.il, 'spectra_x'):
                scope.il.spectra_x.push_state(**{lamp+'_enabled':False for lamp in
                    scope.il.spectra_x.lamp_specs.keys()})
            scope.camera.start_image_sequence_acquisition(frame_count=len(self.exposures)*frames_to_average, trigger_mode='Software')
            for exp in self.exposures:
                images = []
                for i in range(frames_to_average):
                    scope.camera.send_software_trigger()
                    images.append(scope.camera.next_image(max(1000, 2*exp)))
                self.dark_images.append(numpy.mean(images, axis=0))
            scope.camera.end_image_sequence_acquisition()
            if hasattr(scope.il, 'spectra_x'):
                scope.il.spectra_x.pop_state()

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
        if exposure_ms < self.exposures[0] or exposure_ms > self.exposures[-1]:
            raise ValueError('Exposure time is outside of the calibration range')
        i = numpy.searchsorted(self.exposures, exposure_ms)
        if exposure_ms == self.exposures[i]:
            dark_image = self.dark_images[i]
        else:
            before_exp, after_exp = self.exposures[i-1], self.exposures[i]
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
            the several lamps in scope.il.spectra_x)
        max_exposure: longest allowable exposure in ms
        max_intensity: largest allowable lamp intensity
        min_intensity_fraction: least bright value (in terms of the 95th
            percentile of image intensities) allowed for the image to count as
            'properly exposed', as a fraction of the camera bit depth.
            NB: if no other exposure times are valid and not over-exposed, an
            exposure time could be returned that yields images which fall below
            this minimum.
        max_intensity_fraction: brightest value (in terms of maximum image
            intensity, allowing for 11 hot pixels) allowed for the image to
            count as 'properly exposed', as a fraction of the camera bit depth.

    Returns: exposure_time, lamp_intensity
    """
    intensities = numpy.array([255, 224, 192, 160, 128,  96,  64,  32])
    intensities = intensities[intensities <= max_intensity]
    with lamp.in_state(enabled=True):
        scope.camera.start_image_sequence_acquisition(frame_count=len(intensities), trigger_mode='Software')
        bit_depth = int(scope.camera.sensor_gain[:2])
        max_good_value = max_intensity_fraction * (2**bit_depth-1)
        good_intensity = None
        scope.camera.exposure_time = 5 # find a good intensity for a short exposure time (not the shortest! Leave some room for good_exposure to start out underexposed...)
        for intensity in intensities:
            lamp.intensity = intensity
            scope.camera.send_software_trigger()
            image = scope.camera.next_image(1000)
            if image_order_statistic(image, -12) < max_good_value:
                good_intensity = intensity
                break
        if good_intensity is None:
            raise RuntimeError('Could not find a non-overexposed lamp intensity')
    scope.camera.end_image_sequence_acquisition()
    good_exposure = meter_exposure(scope, lamp, max_exposure, min_intensity_fraction, max_intensity_fraction)
    return good_exposure, good_intensity

def meter_exposure(scope, lamp, max_exposure=200, min_intensity_fraction=0.3,
    max_intensity_fraction=0.75):
    """Find an appropriate brightfield exposure setting.

    This function searches through camera exposure times
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
            the several lamps in scope.il.spectra_x)
        max_exposure: longest allowable exposure in ms
        min_intensity_fraction: least bright value (in terms of the 95th
            percentile of image intensities) allowed for the image to count as
            'properly exposed', as a fraction of the camera bit depth.
            NB: if no other exposure times are valid and not over-exposed, an
            exposure time could be returned that yields images which fall below
            this minimum.
        max_intensity_fraction: brightest value (in terms of maximum image
            intensity) allowed for the image to count as 'properly exposed', as
            a fraction of the camera bit depth.

    Returns: exposure_time
    """
    max_exposure_exponent = numpy.log2(max_exposure)
    # Exposure range is set by the curious property of the Zyla camera that
    # short exposures with bright lights yield really noisy images. So avoid
    # exposures < 2 ms...
    # TODO: verify that this is still the case with new cameras once obtained
    exposures = 2**numpy.arange(1, numpy.ceil(max_exposure_exponent)+1)
    exposures[-1] = max_exposure
    with lamp.in_state(enabled=True):
        scope.camera.start_image_sequence_acquisition(frame_count=len(exposures), trigger_mode='Software')
        bit_depth = int(scope.camera.sensor_gain[:2])
        min_good_value = min_intensity_fraction * (2**bit_depth-1)
        max_good_value = max_intensity_fraction * (2**bit_depth-1)
        good_exposure = None
        for exposure in exposures:
            scope.camera.exposure_time = exposure
            scope.camera.send_software_trigger()
            image = scope.camera.next_image(max(1000, 2*exposure))
            image_max = image_order_statistic(image, -12)
            image_min = image_order_statistic(image, int(image.size * 0.95))
            if image_max < max_good_value:
                good_exposure = exposure
            else:
                break
            if image_min > min_good_value:
                break
    if good_exposure is None:
        raise RuntimeError('Could not find a valid exposure time: intensity {}, exposure {}, image max {}, image min {}, max good {}, min good {}'.format(
            lamp.intensity, exposure, image_max, image_min, max_good_value, min_good_value))
    scope.camera.end_image_sequence_acquisition()
    scope.camera.exposure_time = good_exposure
    return good_exposure

def get_vignette_mask(image):
    """Convert a well-exposed image (ideally a brightfield image with ~uniform
    intensity) into a mask delimiting the image region from the dark,
    vignetted borders of the image.

    Returns: vignette_mask, which is True in the image regions.

    """
    likely_vignette_pixels = image[image < numpy.percentile(image, 40)]
    mean, std = mcd.robust_mean_std(likely_vignette_pixels, 0.5)
    vignette_threshold = mean + 150 * std
    vignette_mask = image > vignette_threshold
    vignette_mask = ndimage.binary_fill_holes(vignette_mask)
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
            scope.camera.start_image_sequence_acquisition(frame_count=frames_to_average,
                trigger_mode='Internal')
            images = [scope.camera.next_image() for i in range(frames_to_average)]
            scope.camera.end_image_sequence_acquisition()
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

    Returns: flat-field correction image and the mean intensity of the non-
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
    mean_intensity = flat_field[vignette_mask].mean()
    flat_field /= mean_intensity
    flat_field[flat_field <= 0] = 1 # we're going to reciprocate, so prevent div/0 errors
    flat_field = 1 / flat_field # take reciprocal so that the mask can be used multiplicatively
    flat_field[~vignette_mask] = 0
    return flat_field, mean_intensity


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
