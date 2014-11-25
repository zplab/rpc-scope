import time

from . import scope_configuration
from .io_tool import commands

class AcquisitionSequencer:
    def __init__(self, camera, io_tool, spectra_x):
        self._camera = camera
        self._io_tool = io_tool
        self._spectra_x = spectra_x
    
    def new_sequence(self, readout_rate='280 MHz', **spectra_x_intensities):
        self._steps = []
        self._exposures = []
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
        self._exposures.append(exposure_ms)
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
    
    def run(self):
        assert self._compiled
        self._spectra_x.lamp_intensities(**self._spectra_x_intensities)
        self._camera.start_image_sequence_acquisition(self._num_acquisitions, trigger_mode='External Exposure', 
            overlap=True, auxiliary_out_source='FireAll', pixel_readout_rate=self._readout_rate)
        self._io_tool.start_program()
        names = [self._camera.get_next_image(read_timeout=exposure+1000) for exposure in self._exposures)]
        self._io_tool.wait_for_program_done()
        self._camera.end_image_sequence_acquisition()
        return names