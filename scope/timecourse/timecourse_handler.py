# This code is licensed under the MIT License (see LICENSE file for details)

import numpy
import logging
import time
import datetime

from zplib import background_process
from zplib.image.threaded_io import COMPRESSION

from elegant import process_experiment
from elegant import process_images

from . import base_handler
from ..client_util import autofocus
from ..client_util import calibrate
from ..config import scope_configuration

class BasicAcquisitionHandler(base_handler.TimepointHandler):
    """Base class for most timecourse acquisition needs.

    To create a new timepoint acquisition, the user MUST subclass this class
    from a file that resides INSIDE the desired data-acquisition directory. An
    'experiment_metadata.json' file MUST be created in the same directory,
    containing a dict with keys 'positions', 'z_max', and
    'reference_positions'. The value of 'positions' MUST be a dict mapping
    position names to (x,y,z) stage coords for data acquisition. 'z_max' MUST
    be an single number representing the highest the stage can go during
    autofocus. 'reference_positions' MUST be a list of one or more (x,y,z)
    stage coords to obtain brightfield and fluorescence flatfield reference
    data from.

    The python file implementing the subclass MUST have the following stanza
    at the bottom:
        if __name__ == '__main__':
            MySubclass.main()
    where 'MySubclass' is replaced with whatever the name of the subclass is.

    The experiment_metadata.json file MUST contain entries for 'objective',
    'filter_cube', and 'fluorescence_flatfield_lamp'. If this last is non-null,
    this will be the spectra X lamp that used to obtain fluorescent flatfields.

    The subclass MUST override the get_next_run_interval() method to return
    the desired time interval between the beginning of the current run and
    the beginning of the next. To control the interpretation of this interval,
    the subclass MAY set the INTERVAL_MODE attribute to one of 'scheduled
    start', 'actual start', 'end'. This selects what the starting time for the
    interval before the next run should be: when the job was scheduled to start,
    when it actually started, or when the job ends, respectively.

    The subclass MAY override configure_additional_acquisition_steps() to
    add additional image acquisitions (after the initial default brightfield
    acquisition). The base class docstring shows an example of adding a 200 ms
    GFP exposure, which also requires adding the name of the image file to save
    out to the self.image_names attribute.

    The subclass MUST call self.heartbeat() at least once a minute if any
    overridden functions take more time than that. (The superclass calls
    heartbeat() between calls to these functions.)
    """

    # Potentially useful attributes to override
    REFOCUS_INTERVAL_MINS = 45 # re-run autofocus at least this often. Useful for not autofocusing every timepoint.
    DO_COARSE_FOCUS = False
    # 1 mm distance in 50 steps = 20 microns/step. So we should be somewhere within 20-40 microns of the right plane after the coarse autofocus.
    COARSE_FOCUS_RANGE = 1
    COARSE_FOCUS_STEPS = 50
    # We want to get within 2 microns, so sweep over 90 microns with 45 steps.
    FINE_FOCUS_RANGE = 0.09
    FINE_FOCUS_STEPS = 45
    FINE_FOCUS_SPEED = 0.3
    PIXEL_READOUT_RATE = '100 MHz'
    USE_LAST_FOCUS_POSITION = True # if False, start autofocus from original z position rather than last autofocused position.
    INTERVAL_MODE = 'scheduled start' # Point in time when the countdown to the next run begins: 'scheduled start', 'actual start' or 'end'.
    IMAGE_COMPRESSION = COMPRESSION.DEFAULT # useful options include PNG_FAST, PNG_NONE, TIFF_NONE.
    # If using the FAST or NONE levels, consider using the below option to recompress after the fact.
    RECOMPRESS_IMAGE_LEVEL = None # if not None, start a background job to recompress saved images to the specified level.
    LOG_LEVEL = logging.INFO # logging.DEBUG may be useful
    SEGMENTATION_MODEL = None # name of or path to image-segmentation model to run in the background after the job ends.
    TO_SEGMENT = ['bf'] # image name or names to segment
    AUTOFOCUS_PARAMS = dict(
        metric='brenner',
        metric_kws={}, # use if the metric requires specific keywords; 'brenner' does not
        metric_filter_period_range=None # if not None, (min_size, max_size) tuple for bandpass filtering images before autofocus
    )
    # Values that are unlikely to be useful to override, but may in obscure cases be used:
    TL_FIELD = None # None selects the default for the objective
    TL_APERTURE = None # None selects the default for the objective
    IL_FIELD = None # None selects the default (circle:5), which is the best choice unless you have a compelling reason.

    # Not for overriding
    _IL_FIELD_DEFAULT = 'circle:5'

    def configure_additional_acquisition_steps(self):
        """Add more steps to the acquisition_sequencer's sequence as desired,
        making sure to also add corresponding names to the image_name attribute.
        For example, to add a 200 ms GFP acquisition, a subclass may override
        this as follows:
            def configure_additional_acquisition_steps(self):
                self.scope.camera.acquisition_sequencer.add_step(exposure_ms=200, lamp='cyan')
                self.image_names.append('gfp.png')
        """
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
        raise NotImplementedError()

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
        pass

    # Internal implementation functions are below. Override with care.
    def configure_timepoint(self):
        self.scope.async_ = False
        # in 'TL BF' mode, condenser auto-retracts for 5x objective, and field/aperture get set appropriately
        # on objective switch. That gives a sane-ish default. Then allow specific customization of
        # these values later.
        self.scope.stand.active_microscopy_method = 'TL BF'
        objective = self.experiment_metadata['objective']
        try:
            self.scope.nosepiece.magnification = objective
        except AttributeError:
            # non-motorized nosepiece
            pass
        assert self.scope.nosepiece.magnification == objective

        self.scope.il.shutter_open = True
        self.scope.il.spectra.lamps(**{lamp+'_enabled': False for lamp in self.scope.il.spectra.lamp_specs})
        self.scope.tl.shutter_open = True
        self.scope.tl.lamp.enabled = False
        self.scope.tl.condenser_retracted = objective == 5 # only retract condenser for 5x objective

        config = self.scope.configuration
        tl_field = self.TL_FIELD
        if tl_field is None:
            tl_field = config.stand.TL_FIELD_DEFAULTS[str(objective)]
        self.scope.tl.field_diaphragm = tl_field

        tl_aperture = self.TL_APERTURE
        if tl_aperture is None:
            tl_aperture = config.stand.TL_APERTURE_DEFAULTS[str(objective)]
        self.scope.tl.aperture_diaphragm = tl_aperture

        il_field = self.IL_FIELD
        if il_field is None:
            il_field = self._IL_FIELD_DEFAULT
        self.scope.il.field_wheel = il_field

        self.scope.il.filter_cube = self.experiment_metadata['filter_cube']
        self.scope.camera.sensor_gain = '16-bit (low noise & high well capacity)'
        self.scope.camera.readout_rate = self.PIXEL_READOUT_RATE
        self.scope.camera.shutter_mode = 'Rolling'

        self.scope.camera.autofocus.reset_state() # make sure the autofocus mode cache is clear

        self.configure_calibrations() # sets self.bf_exposure and self.tl_intensity

        self.scope.camera.acquisition_sequencer.new_sequence() # internally sets all spectra x intensities to 255, unless specified here
        self.scope.camera.acquisition_sequencer.add_step(exposure_ms=self.bf_exposure,
            lamp='TL', tl_intensity=self.tl_intensity)
        self.image_names = ['bf.png']
        self.configure_additional_acquisition_steps()

        temperature = target_temperature = None
        humidity = target_humidity = None
        if hasattr(self.scope, 'humidity_controller'):
            # Use the humidity controller temperature: the anova circulator temp measurement gives the
            # internal bath temperature, not the probe temperature...
            try:
                temperature = self.scope.humidity_controller.temperature
                humidity = self.scope.humidity_controller.humidity
                target_humidity = self.scope.humidity_controller.target_humidity
                if hasattr(self.scope, 'temperature_controller'):
                    target_temperature = self.scope.temperature_controller.target_temperature
            except:
                self.logger.error('Could not read humidity or temperature', exc_info=True)
        humidity_log = self.experiment_metadata.setdefault('humidity', {})
        temperature_log = self.experiment_metadata.setdefault('temperature', {})
        humidity_log[self.timepoint_prefix] = dict(humidity=humidity, target_humidity=target_humidity)
        temperature_log[self.timepoint_prefix] = dict(temperature=temperature, target_temperature=target_temperature)

    def configure_calibrations(self):
        self.dark_corrector = calibrate.DarkCurrentCorrector(self.scope)
        ref_positions = self.experiment_metadata['reference_positions']

        # figure out the right brightfield exposure

        # first, go to a good xyz position to look at brightfield exposure
        data_positions = self.experiment_metadata['positions']
        position_name = self.experiment_metadata.get('bf_meter_position_name')
        if position_name is None:
            position_name = sorted(data_positions.keys())[0]
        position_dir, metadata_path, position_metadata = self._position_metadata(position_name)
        x, y, z = data_positions[position_name]
        # see if we have an updated z position to use on...
        for m in position_metadata[::-1]:
            if 'fine_z' in m:
                z = m['fine_z']
                break
        # before  moving the stage, set the scope z to a safe distance so we don't hit anything en route
        safe_z = self.experiment_metadata['z_max'] - 0.5
        self.scope.stage.position = x, y, safe_z
        self.scope.stage.z = z

        # now find a good exposure time and intensity
        self.tl_intensity, self.bf_exposure, actual_bounds, requested_bounds = calibrate.meter_exposure_and_intensity(
            self.scope, self.scope.tl.lamp, max_exposure=32, min_intensity_fraction=0.2, max_intensity_fraction=0.6)
        # make sure that the image is not all dark:
        if actual_bounds[1] < 3000:
            # the almost-brightest point of the image is really dim, when really
            # we wanted it somewhere around 32000. Something's wrong.
            raise RuntimeError('Exposure metering failed to find a sufficiently bright brightfield lamp setting. (Is the lamp on?)')

        self.heartbeat()

        # calculate the BF flatfield image and reference intensity value

        # when moving to the reference slide, again go to a safe z position
        # (don't worry about doing this when moving *on* the reference slide)
        x, y, z = ref_positions[0]
        self.scope.stage.position = x, y, safe_z
        self.scope.stage.z = z

        with self.scope.tl.lamp.in_state(enabled=True):
            exposure = calibrate.meter_exposure(self.scope, self.scope.tl.lamp,
                max_exposure=32, min_intensity_fraction=0.3, max_intensity_fraction=0.85)[0]
            bf_avg = calibrate.get_averaged_images(self.scope, ref_positions, self.dark_corrector, frames_to_average=2)
        vignette_mask = process_images.vignette_mask(self.experiment_metadata['optocoupler'], bf_avg.shape)
        bf_flatfield, bf_ref_intensity = calibrate.get_flat_field(bf_avg, vignette_mask)
        exposure_ratio = self.bf_exposure / exposure
        bf_ref_intensity *= exposure_ratio
        cal_image_names = ['bf_flatfield.tiff']
        cal_images = [bf_flatfield]

        bf_metering = self.experiment_metadata.setdefault('brightfield metering', {})
        bf_metering[self.timepoint_prefix] = dict(ref_intensity=bf_ref_intensity, exposure=self.bf_exposure, intensity=self.tl_intensity)

        self.heartbeat()

        # calculate a fluorescent flatfield if requested
        flatfield_lamp = self.experiment_metadata['fluorescence_flatfield_lamp']
        if flatfield_lamp is not None:
            self.scope.stage.position = ref_positions[0]
            lamp = getattr(self.scope.il.spectra, flatfield_lamp)
            with lamp.in_state(enabled=True):
                fl_exposure, fl_intensity = calibrate.meter_exposure_and_intensity(self.scope, lamp,
                    max_exposure=400, min_intensity_fraction=0.1)[:2]
                fl_avg = calibrate.get_averaged_images(self.scope, ref_positions, self.dark_corrector, frames_to_average=5)
            fl_flatfield, fl_ref_intensity = calibrate.get_flat_field(fl_avg, vignette_mask)
            fl_ref_intensity /= fl_exposure
            cal_image_names.append('fl_flatfield.tiff')
            cal_images.append(fl_flatfield)

            fl_metering = self.experiment_metadata.setdefault('fluorescent metering', {})
            fl_metering[self.timepoint_prefix] = dict(ref_intensity=fl_ref_intensity, fl_flatfield_exposure=fl_exposure, fl_flatfield_intensity=fl_intensity)

        self.heartbeat()

        # save out calibration images
        calibration_dir = self.data_dir / 'calibrations'
        calibration_dir.mkdir(exist_ok=True)
        cal_image_paths = [calibration_dir / (self.timepoint_prefix + ' ' + name) for name in cal_image_names]
        if self.write_files:
            self.image_io.write(cal_images, cal_image_paths)

        self.scope.camera.exposure_time = self.bf_exposure
        # return to a safe z position
        self.scope.stage.z = safe_z

    def get_next_run_time(self):
        interval_mode = self.INTERVAL_MODE
        assert interval_mode in {'scheduled start', 'actual start', 'end'}
        timestamps = self.experiment_metadata['timestamps']
        elapsed_sec = timestamps[-1] - timestamps[0]# time since beginning of timecourse
        elapsed_hours = elapsed_sec / 60**2
        interval_hours = self.get_next_run_interval(elapsed_hours)
        interval_seconds = interval_hours * 60**2
        if interval_hours is None:
            return None
        if interval_mode == 'scheduled start':
            seconds_delayed = self.start_time - self.scheduled_start
            if seconds_delayed > interval_seconds:
                # we've fallen more than a full cycle behind!
                # keep the relative phase of the cycle, but skip all the
                # cycles that we've lost.
                phase = seconds_delayed % interval_seconds
                start = self.start_time - phase
            else:
                start = self.scheduled_start

        elif interval_mode == 'actual start':
            start = self.start_time
        else:
            start = self.end_time
        return start + interval_seconds

    def run_autofocus(self, position_name, return_images=False):
        z_start = self.scope.stage.z
        z_max = self.experiment_metadata['z_max']
        with self.heartbeat_timer(), self.scope.tl.lamp.in_state(enabled=True):
            coarse_z = None
            if self.DO_COARSE_FOCUS:
                with self.scope.camera.in_state(binning='4x4', exposure_time=self.scope.camera.exposure_time/16):
                    coarse_z, focus_scores, focus_images = autofocus.autofocus(self.scope,
                        z_start, z_max, self.COARSE_FOCUS_RANGE, self.COARSE_FOCUS_STEPS,
                        speed=0.8, **self.AUTOFOCUS_PARAMS)
                z_start = coarse_z
            mask_file = self.data_dir / 'Focus Masks' / (position_name + '.png')
            mask = str(mask_file) if mask_file.exists() else None
            if mask:
                self.logger.info('Using autofocus mask: {}', mask)
            fine_z, focus_scores, focus_images = autofocus.autofocus(self.scope,
                z_start, z_max, self.FINE_FOCUS_RANGE, self.FINE_FOCUS_STEPS,
                speed=self.FINE_FOCUS_SPEED, return_images=return_images,
                metric_mask=mask, **self.AUTOFOCUS_PARAMS)
        return coarse_z, fine_z, focus_scores, focus_images

    def acquire_images(self, position_name, position_dir, position_metadata):
        self.scope.camera.exposure_time = self.bf_exposure
        self.scope.tl.lamp.intensity = self.tl_intensity
        metadata = {}
        last_autofocus_time = 0
        if self.USE_LAST_FOCUS_POSITION:
            last_z = None
            for m in position_metadata[::-1]:
                if 'fine_z' in m:
                    last_autofocus_time = m['timestamp']
                    last_z = m['fine_z']
                    break
            if last_z is not None:
                self.scope.stage.z_from_offset(z, direction=-1) # approach from below always

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
                    self.scope.stage.z_from_offset(z, direction=-1) # approach from below always
                    metadata['fine_z'] = z
                    override_autofocus = True

        save_focus_stack = False
        if not override_autofocus and time.time() - last_autofocus_time > self.REFOCUS_INTERVAL_MINS * 60:
            if position_name in self.experiment_metadata.get('save_focus_stacks', []):
                save_focus_stack = True
            with self.debug_timing('Autofocus'):
                coarse_z, fine_z, focus_scores, focus_images = self.run_autofocus(position_name, save_focus_stack)
            if coarse_z is not None:
                metadata['coarse_z'] = coarse_z
            metadata['fine_z'] = fine_z
            self.logger.info('Autofocus z: {}', fine_z)
        metadata['stage_z'] = self.scope.stage.z
        with self.debug_timing('Acquisition sequence'):
            images = self.scope.camera.acquisition_sequencer.run()
        exposures = self.scope.camera.acquisition_sequencer.exposure_times
        timestamps = list(self.scope.camera.acquisition_sequencer.latest_timestamps)
        self.post_acquisition_sequence(position_name, position_dir, position_metadata, metadata, images, exposures, timestamps)
        images = [self.dark_corrector.correct(image, exposure) for image, exposure in zip(images, exposures)]
        if None in timestamps:
            self.logger.warning('None value found in timestamp! Timestamps = {}', timestamps)
            timestamps = [t if t is not None else numpy.nan for t in timestamps]
        timestamps = (numpy.array(timestamps) - timestamps[0]) / self.scope.camera.timestamp_hz
        metadata['image_timestamps'] = dict(zip(self.image_names, timestamps))

        if save_focus_stack and self.write_files:
            save_image_dir = position_dir / f'{self.timepoint_prefix} focus'
            save_image_dir.mkdir(exist_ok=True)
            pad = int(numpy.ceil(numpy.log10(self.FINE_FOCUS_STEPS - 1)))
            image_paths = [save_image_dir / f'{i:0{pad}}.png' for i in range(self.FINE_FOCUS_STEPS)]
            z, scores = zip(*focus_scores)
            focus_data = dict(z=z, scores=scores, best_index=numpy.argmax(scores))
            self._write_atomic_json(save_image_dir / 'focus_data.json', focus_data)
            self.image_io.write(focus_images, image_paths, self.IMAGE_COMPRESSION)

        return images, self.image_names, metadata

    def cleanup(self):
        # use separate locks to let compression and segmentation run in parallel
        # but prevent multiple compression or segmentation jobs from piling up
        if self.RECOMPRESS_IMAGE_LEVEL is not None:
            logfile = self.data_dir / 'compress.log'
            lock = scope_configuration.CONFIG_DIR / 'compress_job'
            background_process.run_in_background(process_experiment.compress_pngs,
                experiment_root=self.data_dir, timepoints=[self.timepoint_prefix],
                level=self.RECOMPRESS_IMAGE_LEVEL,
                nice=20, delete_logfile=False, logfile=logfile, lock=lock)

        if self.SEGMENTATION_MODEL is not None:
            # ask to segment all un-segmented images for all timepoints, just to
            # make sure everything gets segmented. Thus, even if a background
            # segmentation job dies midway, the files will get picked up the
            # next time...
            logfile = self.data_dir / 'segment.log'
            lock = scope_configuration.CONFIG_DIR / 'segment_job'
            background_process.run_in_background(process_experiment.segment_experiment,
                experiment_root=self.data_dir, model=self.SEGMENTATION_MODEL,
                channels=self.TO_SEGMENT, overwrite_existing=False,
                nice=20, delete_logfile=False, logfile=logfile, lock=lock)
