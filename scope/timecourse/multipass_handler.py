import collections
import pathlib
from scope.timecourse import timecourse_handler

class MultiPassHandler(timecourse_handler.BasicAcquisitionHandler):
    '''
        This Handler performs multiple passes of the same image (and post-) acquisition sequence.
    '''
    ACQUISITON_INTERVAL_HOURS = 3
    REFOCUS_INTERVAL_MINS = self.ACQUISITON_INTERVAL_HOURS*60 # chain autofocusing to acquisition
    DO_COARSE_FOCUS = False

    FINE_FOCUS_RANGE = 0.05
    FINE_FOCUS_STEPS = 25
    PIXEL_READOUT_RATE = '100 MHz'
    USE_LAST_FOCUS_POSITION = True # if False, start autofocus from original z position rather than last autofocused position.
    INTERVAL_MODE = 'scheduled start'
    IMAGE_COMPRESSION = timecourse_handler.PNG_FAST
    LOG_LEVEL = timecourse_handler.logging.INFO

    FLUORESCENCE_FLATFIELD_LAMP_AF = 'green_yellow'
    DEVELOPMENT_TIME_HOURS = 45
    REVISIT_INTERVAL_MINS = 3
    NUM_TOTAL_VISITS = 7

    def configure_additional_acquisition_steps(self):
        if self.start_time - self.experiment_metadata['timestamps'][0] > self.DEVELOPMENT_TIME_HOURS*3600:
            self.scope.camera.acquisition_sequencer.add_step(exposure=50,lamp=self.FLUORESCENCE_FLATFIELD_LAMP_AF)
            self.image_names.append('autofluorescence.png')

    def finalize_acquisition(self, position_name):
        try:
            self.acquire_z
        except NameError:
            self.acquire_z = {}
        self.acquire_z[position_name] = self.scope.stage.z

    def run_all_positions(self):
        for position_name, position_coords in sorted(self.positions.items()):
            if position_name not in self.skip_positions:
                self.run_position(position_name, position_coords)
                self.heartbeat()
        #super

        self.scope.camera.acquisition_sequencer.new_sequence() # internally sets all spectra x intensities to 255, unless specified here
        self.scope.camera.acquisition_sequencer.add_step(exposure_ms=self.bf_exposure,
            lamp='TL', tl_intensity=self.tl_intensity)
        self.image_names = [f'bf_{visit_num}.png']

        for visit_num in range(self.NUM_TOTAL_VISITS):
            pass_start = time.time()
            for position_name in self.positions()
                if position_name not in self.skip_positions:
                    position_coords = self.positions[position_name][:-1] + [self.acquire_z[position_name]]
                    position_dir, metadata_path, position_metadata = self._position_metadata(position_name)
                    self.logger.info(f'Acquiring Position: {position_name} - visit {visit_num+1}')
                    self.scope.stage.position = position_coords
                    images = self.scope.camera.acquisition_sequencer.run()
                    exposures = self.scope.camera.acquisition_sequencer.exposure_times
                    timestamps = list(self.scope.camera.acquisition_sequencer.latest_timestamps) # Don't zero-justify timestamps for posterity.
                    images = [self.dark_corrector.correct(image, exposure) for image, exposure in zip(images, exposures)]

                    position_metadata['image_timestamps'].update(zip(self.image_names, timestamps))
                    image_paths = [position_dir / (self.timepoint_prefix + ' ' + name) for name in self.image_names]

                    futures_out = self.image_io.write(images, image_paths, self.IMAGE_COMPRESSION, wait=False)
                    self._job_futures.extend(futures_out)
                    self._write_atomic_json(metadata_path, position_metadata)

                    self.heartbeat()
            self.logger.debug(f'Pass {visit_num+1} completed in {time.time()-pass_time} s')
            try:
                time.sleep(self.REVISIT_INTERVAL_MINS-(time.time()-pass_start)*60)
            except ValueError: # Negative values
                pass


    def get_next_run_interval(self, experiment_hours):
        return self.ACQUISITON_INTERVAL_HOURS

if __name__ == '__main__':
    # note: can add any desired keyword arguments to the Handler init method
    # to the below call to main(), which is defined by scope.timecourse.base_handler.TimepointHandler
    MultiPassHandler.main(pathlib.Path(__file__).parent)
