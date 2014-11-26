from . import camera
import numpy
import ism_buffer_utils

def brenner(array, z):
    x_diffs = (array[2:, :] - array[:-2, :])**2
    y_diffs = (array[:, 2:] - array[:, :-2])**2
    return x_diffs.sum() + y_diffs.sum()

METRICS = {'brenner': brenner}

class Autofocus:
    def __init__(self, camera, stage):
        self._camera = camera
        self._stage = stage
    
    def autofocus(self, start, end, steps, metric='brenner'):
        metric = METRICS[metric]
        read_timeout = self._camera.get_exposure_time()
        self._camera.start_image_sequence_acquisition(steps, trigger_mode='Software', pixel_readout_rate='280 MHz')
        focus_values = []
        async = self._stage.get_async()
        self._stage.set_async(False)
        for z in numpy.linspace(start, end, steps):
            self._stage.set_z(z)
            self._camera.send_software_trigger()
            name = self._camera.get_next_image(read_timeout)
            array = ism_buffer_utils._server_release_array(name)
            focus_values.append((metric(array, z), z))
        self._camera.end_image_sequence_acquisition()
        focus_values.sort()
        self._stage.set_z(focus_values[-1][1]) # go to focal plane with highest score
        self._stage.set_async(async)