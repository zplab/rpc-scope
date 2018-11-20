# This code is licensed under the MIT License (see LICENSE file for details)

import numpy
import time
import contextlib

def z_stack(scope, mm_range, num_steps, tl_enabled=False, **spectra_state):
    """Acquire a z-series of images.

    Parameters:
        scope: microscope client object
        mm_range: number of mm around the current focus position to collect the
            z-stack. The range will be the current focus positon +/- mm_range/2.
        num_steps: number of focus steps within the range to acquire.
        tl_enabled: should the transmitted lamp be enabled during acquisition?
        spectra_state: state of the spectra x during acquisition (see
         documentation for scope.il.spectra.lamps for parameter description; a
         simple example would be 'cyan_enabled=True' to turn on the cyan lamp.)

    Returns: images, z_positions

    """
    z = scope.stage.z
    z_positions = numpy.linspace(z - mm_range/2, z + mm_range/2, num_steps)
    images = []
    exposure_sec = scope.camera.exposure_time / 1000
    with scope.camera.image_sequence_acquisition(num_steps, trigger_mode='Software'), scope.stage.in_state(async=True):
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
            with contextlib.ExitStack() as stack:
                stack.enter_context(scope.tl.lamp.in_state(enabled=tl_enabled))
                if spectra_state:
                    stack.enter_context(scope.il.spectra.in_state(**spectra_state))
                scope.camera.send_software_trigger()
                time.sleep(exposure_sec)
        images.append(scope.camera.next_image(read_timeout_ms=1000))
    return images, z_positions
