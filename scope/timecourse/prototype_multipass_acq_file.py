import pathlib
from scope.timecourse import timecourse_handler

class Handler(timecourse_handler.BasicAcquisitionHandler):
    FILTER_CUBE = $filter_cube
    FLUORESCENCE_FLATFIELD_LAMP = $fl_flatfield_lamp
    OBJECTIVE = 10
    REFOCUS_INTERVAL_MINS = 45 # re-run autofocus at least this often. Useful for not autofocusing every timepoint.
    DO_COARSE_FOCUS = False
    # 1 mm distance in 50 steps = 20 microns/step. So we should be somewhere within 20-40 microns of the right plane after coarse autofocus.
    COARSE_FOCUS_RANGE = 1
    COARSE_FOCUS_STEPS = 50
    # We want to get within 2 microns, so sweep over 90 microns with 45 steps.
    FINE_FOCUS_RANGE = 0.09
    FINE_FOCUS_STEPS = 45
    PIXEL_READOUT_RATE = '100 MHz'
    USE_LAST_FOCUS_POSITION = True # if False, start autofocus from original z position rather than last autofocused position.
    INTERVAL_MODE = 'scheduled start'
    IMAGE_COMPRESSION = timecourse_handler.COMPRESSION.DEFAULT # useful options include PNG_FAST, PNG_NONE, TIFF_NONE.
    # If using the FAST or NONE levels, consider using the below option to recompress after the fact.
    RECOMPRESS_IMAGE_LEVEL = None # if not None, start a background job to recompress saved images to the specified level.
    LOG_LEVEL = timecourse_handler.logging.INFO # DEBUG may be useful
    # Set the following to have the script set the microscope apertures as desired:
    TL_FIELD_DIAPHRAGM = None
    TL_APERTURE_DIAPHRAGM = None
    IL_FIELD_WHEEL = None # 'circle:3' is a good choice.
    VIGNETTE_PERCENT = 5 # 5 is a good number when using a 1x optocoupler. If 0.7x, use 35.

    REVISIT_INTERVAL_MINS = 15

    def configure_additional_acquisition_steps(self):
        """Add more steps to the acquisition_sequencer's sequence as desired,
        making sure to also add corresponding names to the image_name attribute.
        For example, to add a 200 ms GFP acquisition, a subclass may override
        this as follows:
            def configure_additional_acquisition_steps(self):
                self.scope.camera.acquisition_sequencer.add_step(exposure_ms=200,
                    lamp='cyan')
                self.image_names.append('gfp.png')
        """
        pass

    def run_timepoint(self, scheduled_start):
        try:
            self.heartbeat()
            self.timepoint_prefix = time.strftime('%Y-%m-%dt%H%M')
            self.scheduled_start = scheduled_start
            self.start_time = time.time()
            self._job_futures = []
            self.logger.info('Starting timepoint {} ({:.0f} minutes after scheduled)', self.timepoint_prefix,
                (self.start_time-self.scheduled_start)/60)
            # record the timepoint prefix and timestamp for this timepoint into the
            # experiment metadata
            self.experiment_metadata.setdefault('timepoints', []).append(self.timepoint_prefix)
            self.experiment_metadata.setdefault('timestamps', []).append(self.start_time)
            self.configure_timepoint()
            self.heartbeat()

            revisit_queue = []
            for position_name, position_coords in sorted(self.positions.items()):
                if revisit_queue:
                    # Check queue for things to run (time.time < previuos value?)
                    # if something to run
                    self.run_position(position_to_run,prev_position_coords, False)

                if position_name not in self.skip_positions:
                    self.run_position(position_name, position_coords,True)

                    # TODO: Read in the recently made metadata and grab position coords
                    revisit_queue.append({'position':position_name,'position_coords':, 'revisit_time':time.time()+REVISIT_INTERVAL_MINS*3600}) # TODO pull coords from last entry in metadata (assume written)
                    self.heartbeat()


            self.finalize_timepoint()
            self.heartbeat()
            self.end_time = time.time()
            self.experiment_metadata.setdefault('durations', []).append(self.end_time - self.start_time)
            if self.write_files:
                self._write_atomic_json(self.experiment_metadata_path, self.experiment_metadata)
            run_again = self.skip_positions != self.positions.keys() # don't run again if we're skipping all the positions
            if self._job_futures:
                self.logger.debug('Waiting for background jobs')
                t0 = time.time()
                # wait for all queued background jobs to complete.
                not_done = self._job_futures
                while not_done:
                    # send heartbeats while we wait for futures to finish
                    done, not_done = futures.wait(not_done, timeout=60)
                    self.heartbeat()
                # now get the result() from each future, which will raise any errors encountered
                # during the execution.
                [f.result() for f in self._job_futures]
                self.logger.debug('Background jobs complete ({:.1f} seconds)', time.time()-t0)
            self.cleanup()
            # transfer timepoint information to annotations dicts
            process_data.annotate(self.data_dir, [process_data.annotate_timestamps])

            self.logger.info('Timepoint {} ended ({:.0f} minutes after starting)', self.timepoint_prefix,
                             (time.time()-self.start_time)/60)
            if run_again:
                return self.get_next_run_time()
        except:
            self.logger.error('Exception in timepoint:', exc_info=True)
            raise

    def run_position(self, position_name, position_coords,revisiting):
        """Do everything required for taking a timepoint at a single position
        EXCEPT focusing / image acquisition. This includes moving the stage to
        the right x,y position, loading and saving metadata, and saving image
        data, as generated by acquire_images()"""

        '''
            Things to Do:
                - Make sure that the position_metadata doesn't have two entries written to it per timepoint
                - For second run through, add additional appropriate metadata
                - Make another acquire images for the second run through (make sure the new images have different names)
        '''

        self.logger.info('Acquiring Position: {}', position_name)
        t0 = time.time()
        timestamp = time.time()
        position_dir, metadata_path, position_metadata = self._position_metadata(position_name)
        position_dir.mkdir(exist_ok=True)
        if self.scope is not None:
            self.scope.stage.position = position_coords
        t1 = time.time()
        self.logger.debug('Stage Positioned ({:.1f} seconds)', t1-t0)
        images, image_names, new_metadata = self.acquire_images(position_name, position_dir,
            position_metadata, revisiting)
        t2 = time.time()
        self.logger.debug('{} Images Acquired ({:.1f} seconds)', len(images), t2-t1)
        image_paths = [position_dir / (self.timepoint_prefix + ' ' + name) for name in image_names]
        if new_metadata is None:
            new_metadata = {}
        new_metadata['timestamp'] = timestamp # TODO Here!
        new_metadata['timepoint'] = self.timepoint_prefix
        position_metadata.append(new_metadata) # TODO Here!
        if self.write_files:
            futures_out = self.image_io.write(images, image_paths, self.IMAGE_COMPRESSION, wait=False)
            self._job_futures.extend(futures_out)
            self._write_atomic_json(metadata_path, position_metadata)
        t3 = time.time()
        self.logger.debug('Images saved ({:.1f} seconds)', t3-t2)
        self.logger.debug('Position done (total: {:.1f} seconds)', t3-t0)

    def acquire_images(self, position_name, position_dir, position_metadata, revisiting):

        '''
            Things to do":
                - Don't autofocus the second time
                - Rename your images differently the second time
        '''

        t0 = time.time()
        self.scope.camera.exposure_time = self.bf_exposure
        self.scope.tl.lamp.intensity = self.tl_intensity
        metadata = {}
        last_autofocus_time = 0
        if self.USE_LAST_FOCUS_POSITION:
            last_z = self.positions[position_name][2]
            for m in position_metadata[::-1]:
                if 'fine_z' in m:
                    last_autofocus_time = m['timestamp']
                    last_z = m['fine_z']
                    break
            self.scope.stage.z = last_z

        override_autofocus = False
        z_updates = self.experiment_metadata.get('z_updates', {})
        if len(z_updates) > 0:
            latest_update_isotime = sorted(z_updates.keys())[-1]
            last_autofocus_isotime = datetime.datetime.fromtimestamp(last_autofocus_time).isoformat()
            if latest_update_isotime > last_autofocus_isotime:
                latest_z_update = z_updates[latest_update_isotime]
                if position_name in latest_z_update:
                    z = latest_z_update[position_name]
                    self.logger.info('Using updated z: {}', z)
                    self.scope.stage.z = z
                    metadata['fine_z'] = z
                    override_autofocus = True

        save_focus_stack = False
        if not override_autofocus and t0 - last_autofocus_time > self.REFOCUS_INTERVAL_MINS * 60:
            if position_name in self.experiment_metadata.get('save_focus_stacks', []):
                save_focus_stack = True
            best_z, focus_scores, focus_images = self.run_autofocus(position_name, metadata, save_focus_stack)
            t1 = time.time()
            self.logger.debug('Autofocused ({:.1f} seconds)', t1-t0)
            self.logger.info('Autofocus z: {}', metadata['fine_z'])
        else:
            t1 = time.time()

        images = self.scope.camera.acquisition_sequencer.run()
        t2 = time.time()
        self.logger.debug('Acquisition sequence run ({:.1f} seconds)', t2-t1)
        exposures = self.scope.camera.acquisition_sequencer.exposure_times
        timestamps = list(self.scope.camera.acquisition_sequencer.latest_timestamps)
        self.post_acquisition_sequence(position_name, position_dir, position_metadata, metadata, images, exposures, timestamps)
        images = [self.dark_corrector.correct(image, exposure) for image, exposure in zip(images, exposures)]
        if None in timestamps:
            self.logger.warning('None value found in timestamp! Timestamps = {}', timestamps)
            timestamps = [t if t is not None else numpy.nan for t in timestamps]
        timestamps = (numpy.array(timestamps) - timestamps[0]) / self.scope.camera.timestamp_hz
        metadata['image_timestamps']=dict(zip(self.image_names, timestamps))

        if save_focus_stack and self.write_files:
            save_image_dir = position_dir / f'{self.timepoint_prefix} focus'
            save_image_dir.mkdir(exist_ok=True)
            pad = int(numpy.ceil(numpy.log10(self.FINE_FOCUS_STEPS - 1)))
            image_paths = [save_image_dir / f'{i:0{pad}}.png' for i in range(self.FINE_FOCUS_STEPS)]
            z, scores = zip(*focus_scores)
            focus_data = dict(z=z, scores=scores, best_index=numpy.argmax(scores))
            self._write_atomic_json(save_image_dir / 'focus_data.json', focus_data)
            with self.heartbeat_timer():
                self.image_io.write(focus_images, image_paths, self.IMAGE_COMPRESSION)

        return images, self.image_names, metadata

    def post_acquisition_sequence(self, position_name, position_dir, position_metadata, current_timepoint_metadata, images, exposures, timestamps):
        """Run any necessary image acquisitions, etc, after the main acquisition
        sequence finishes. (E.g. for light stimulus and post-stimulus recording.)

        Parameters:
            position_name: name of the position in the experiment metadata file.
            position_dir: pathlib.Path object representing the directory where
                position-specific data files and outputs are written. Useful for
                reading previous image data.
            position_metadata: list of all the stored position metadata from the
                previous timepoints, in chronological order.
            current_timepoint_metadata: the metatdata for the current timepoint.
                It may be used to append to keys like 'image_timestamps' etc.
            images: list of acquired images. Newly-acquired images should be
                appended to this list.
            exposures: list of exposure times for acquired images. If additional
                images are acquired, their exposure times should be appended.
            timestamps: list of camera timestamps for acquired images. If
                additional images are acquired, their timestamps should be appended.
        """
        # remember to call self.heartbeat() at least once every minute or so
        pass

    def get_next_run_interval(self, experiment_hours):
        """Return the delay interval, in hours, before the experiment should be
        run again.

        The interval will be interpreted according to the INTERVAL_MODE attribute,
        as described in the class documentation. Returning None indicates that
        timepoints should not be acquired again.

        Parameters:
            experiment_hours: number of hours between the start of the first
                timepoint and the start of this timepoint.
        """
        return $run_interval

if __name__ == '__main__':
    # note: can add any desired keyword arguments to the Handler init method
    # to the below call to main(), which is defined by scope.timecourse.base_handler.TimepointHandler
    Handler.main(pathlib.Path(__file__).parent)
