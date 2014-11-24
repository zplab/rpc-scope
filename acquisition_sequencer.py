import time

from . import scope_configuration
from .io_tool import commands
from . import ism_buffer_utils
from .andor import lowlevel

class AcquisitionSequencer:
    def __init__(self, camera, io_tool, spectra_x):
        self._camera = camera
        self._io_tool = io_tool
        self._spectra_x = spectra_x
    
    def new_sequence(self, readout_rate='280 MHz', **spectra_x_intensities):
        self._steps = []
        self._compiled = False
        # set the wait time low because we have clean shielded cables
        self._steps.append(commands.wait_time(2))
        # turn off all the spectra x lamps
        self._steps.append(commands.lumencor_lamps(**{lamp:False for lamp in scope_configuration.IOTool.LUMENCOR_PINS.keys()}))
        self._spectra_x_intensities = spectra_x_intensities
        self._readout_rate = readout_rate
        self._num_acquisitions = 0
        
    def add_step(self, exposure_ms, tl_enable=None, tl_intensity=None, **spectra_x_lamps):
        self._num_acquisitions += 1
        lamps = {lamp:True for lamp, value in spectra_x_lamps.items() if value}
        self._steps.append(commands.wait_high(scope_configuration.IOTool.CAMERA_PINS['arm']))
        self._steps.append(commands.set_high(scope_configuration.IOTool.CAMERA_PINS['trigger']))
        self._steps.append(commands.set_low(scope_configuration.IOTool.CAMERA_PINS['trigger']))
        self._steps.append(commands.wait_high(scope_configuration.IOTool.CAMERA_PINS['AuxOut1'])) # set to 'FireAll'
        self._steps.append(commands.transmitted_lamp(tl_enable, tl_intensity))
        self._steps.append(commands.lumencor_lamps(**lamps))
        if exposure_ms <= 65.535:
            self._steps.append(commands.delay_us(int(round(exposure_ms*1000))-4)) # delay command itself takes 4 µs, so subtract off 4
        else:
            self._steps.append(commands.delay_ms(int(round(exposure_ms))))
        if tl_enable:
            self._steps.append(commands.transmitted_lamp(enable=False))
        self._steps.append(commands.lumencor_lamps(**{lamp:False for lamp in lamps})) # turn lamps back off
        
    def compile(self):
        assert self._num_acquisitions > 0
        # send one last trigger to end the final acquisition
        self._steps.append(commands.wait_high(scope_configuration.IOTool.CAMERA_PINS['arm']))
        self._steps.append(commands.set_high(scope_configuration.IOTool.CAMERA_PINS['trigger']))
        self._steps.append(commands.set_low(scope_configuration.IOTool.CAMERA_PINS['trigger']))
        
        steps = [s for s in self._steps if s] # filter out empty steps
        self._io_tool.store_program(steps)
        self._compiled = True
    
    def run_sequence(self):
        assert self._compiled
        self._spectra_x.lamp_intensities(**self._spectra_x_intensities)
        t = time.time()
        names = ['sequence@{}-{}'.format(t, i) for i in range(self._num_acquisitions)]
        input_buffers, output_arrays, convert_buffers = zip(*map(self._camera._make_input_output_buffers, names))
        with self._camera._live_guarded():
            lowlevel.Flush()
            self._camera.push_state(overlap=True, cycle_mode='Fixed', frame_count=frames,
                trigger_mode='External Exposure', auxiliary_out_source='FireAll', pixel_readout_rate=self._readout_rate)
            for ib in input_buffers:
                lowlevel.queue_buffer(ib)
            lowlevel.Command('AcquisitionStart')
            self._io_tool.start_program()
            self._io_tool.wait_for_program_done()
            lowlevel.Command('AcquisitionStop')
            lowlevel.Flush()
            self._camera.pop_state()
        for cb in convert_buffers:
            cb()
        for name, output_array in zip(names, output_arrays):
            ism_buffer_utils.server_register_array(name, output_array)
        return names