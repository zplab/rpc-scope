# This code is licensed under the MIT License (see LICENSE file for details)

import pathlib
import datetime
import json
import numpy
from scipy import spatial

from PyQt5 import Qt
from zplib import datafile
from zplib import fit_affine
import freeimage
from ris_widget.overlay import roi
from ris_widget import layer

from ..gui import scope_viewer_widget
from . import metadata_util

handler_template = \
'''import pathlib
import logging
from scope.timecourse import timecourse_handler
from zplib.image.threaded_io import COMPRESSION

class Handler(timecourse_handler.BasicAcquisitionHandler):
    # Potentially useful attributes to modify
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
    INTERVAL_MODE = 'scheduled start' #point in time when the countdown to the next run begins: 'scheduled start', 'actual start' or 'end'.
    IMAGE_COMPRESSION = COMPRESSION.DEFAULT # useful options include PNG_FAST, PNG_NONE, TIFF_NONE.
    # If using the FAST or NONE levels, consider using the below option to recompress after the fact.
    RECOMPRESS_IMAGE_LEVEL = None # if not None, start a background job to recompress saved images to the specified level.
    LOG_LEVEL = logging.INFO # logging.DEBUG may be useful
    SEGMENTATION_MODEL = None # name of or path to image-segmentation model to run in the background after the job ends.
    TO_SEGMENT = ['bf'] # image name or names to segment
    AUTOFOCUS_PARAMS = dict(
        metric='brenner',
        metric_kws={{}}, # use if the metric requires specific keywords; 'brenner' does not
        metric_filter_period_range=None # if not None, (min_size, max_size) tuple for bandpass filtering images before autofocus
    )
    # Values that are unlikely to be useful to modify, but may in obscure cases be used:
    TL_FIELD = None # None selects the default for the objective
    TL_APERTURE = None # None selects the default for the objective
    IL_FIELD = None # None selects the default (circle:5), which is the best choice unless you have a compelling reason.

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
        return {run_interval!r}

if __name__ == '__main__':
    # note: can add any desired keyword arguments to the Handler init method
    # to the below call to main(), which is defined by scope.timecourse.base_handler.TimepointHandler
    Handler.main(pathlib.Path(__file__).parent)
'''

def create_acquire_file(data_dir, run_interval):
    """Create a skeleton acquisition file for timecourse acquisitions.

    Parameters:
        data_dir: directory to write python file into
        run_interval: desired number of hours between starts of timepoint
            acquisitions.
    """
    data_dir = pathlib.Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    code = handler_template.format(run_interval=run_interval)
    with (data_dir / 'acquire.py').open('w') as f:
        f.write(code)

def create_metadata_file(data_dir, positions, z_max, reference_positions,
        nominal_temperature, objective, optocoupler, filter_cube,
        fluorescence_flatfield_lamp, save_focus_stacks=None, **other_metadata):
    """ Create the experiment_metadata.json file for timecourse acquisitions.

    Parameters:
        data_dir: directory to write metadata file into
        positions: list of (x,y,z) positions, OR dict mapping different category
            names to lists of (x,y,z) positions.
        z_max: maximum z-value allowed during autofocus
        reference_positions: list of (x,y,z) positions to be used to generate
            brightfield and optionally fluorescence flat-field images.
        nominal_temperature: intended temperature for experiment
        objective, optocoupler: objective and optocoupler to be used.
        filter_cube: name of the filter cube to use
        fluorescence_flatfield_lamp: if fluorescent flatfield images are
            desired, provide the name of an appropriate spectra x lamp that is
            compatible with the specified filter cube. Use None to disable
            fluorescence flatfielding.
        save_focus_stacks: if None, don't save any focus stacks. If a list of position
            names, save focus stacks for those positions. If a number, save
            focus stacks for that number of positions.
        **other_metadata: key-values that will be saved directly in metadata json.
    """
    data_dir = pathlib.Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        items = positions.items()
    except AttributeError:
        items = [('', positions)]
    named_positions = {}
    for name_prefix, positions in items:
        names = _name_positions(len(positions), name_prefix)
        named_positions.update(zip(names, positions))
    bf_meter_position_name = _choose_bf_metering_pos(named_positions)
    metadata = dict(z_max=z_max, reference_positions=reference_positions,
        positions=named_positions, bf_meter_position_name=bf_meter_position_name,
        objective=int(objective), optocoupler=float(optocoupler),
        nominal_temperature=float(nominal_temperature), filter_cube=str(filter_cube),
        fluorescence_flatfield_lamp=fluorescence_flatfield_lamp, **other_metadata)
    if save_focus_stacks:
        try:
            # check if it's iterable
            for pos in save_focus_stacks:
                assert pos in named_positions
        except TypeError:
            num_to_save = int(save_focus_stacks)
            save_indices = numpy.random.permutation(len(named_positions))[:num_to_save]
            names = list(named_positions.keys())
            save_focus_stacks = [names[i] for i in save_indices]
        metadata['save_focus_stacks'] = save_focus_stacks
    with (data_dir / 'experiment_metadata.json').open('w') as f:
        datafile.json_encode_legible_to_file(metadata, f)

def _choose_bf_metering_pos(positions):
    # find the position which has the smallest distance to its 8 closest neighbors,
    # because that position is likely right in the middle
    pos_names, pos_values = zip(*positions.items())
    xys = numpy.array(pos_values)[:,:2]
    distances = spatial.distance_matrix(xys, xys)
    distances.sort(axis=1)
    distance_sums = distances[:,:8].sum(axis=1)
    return pos_names[distance_sums.argmin()]

def simple_get_positions(scope):
    """Return a list of interactively-obtained scope stage positions."""
    _maybe_reinit_stage(scope)
    positions = []
    print('Press enter after each position has been found; press control-c to end')
    while True:
        try:
            input()
        except KeyboardInterrupt:
            break
        positions.append(scope.stage.position)
        print('Position {}: {}'.format(len(positions), tuple(positions[-1])), end='')
    return positions

def _name_positions(num_positions, name_prefix):
    pad = int(numpy.ceil(numpy.log10(max(1, num_positions-1))))
    names = [f'{name_prefix}{i:0{pad}}' for i in range(num_positions)]
    return names

def _maybe_reinit_stage(scope):
    reinit = input('press y and enter to reinitialize the stage; press enter to skip reinit. ')
    if reinit.lower() == 'y':
        current_position = scope.stage.x, scope.stage.y
        scope.stage.reinit_x()
        scope.stage.reinit_y()
        scope.stage.x, scope.stage.y = current_position

def get_positions_with_roi(scope, roi_class=roi.EllipseROI, **roi_kws):
    """Interactively obtain scope stage positions and an elliptical ROI for each.

    A viewer showing the live scope image is displayed, with a movable, resizable
    ellipse. Once the ellipse is placed over the desired focus region of the
    image, press enter in the terminal to record that position and ROI.

    NOTE: focus ROIs are used ONLY in fine-focus-only mode. They will be ignored
    if DO_COARSE_FOCUS is True.

    Parameters:
        scope: microscope object
        focus_roi: ROI object to use

    Returns: positions, rois
        positions: list of (x, y, z) positions
        rois: list of Qt.QRectF objects describing the ROI for each position.
        roi_class: class of ROI to use for display
    """
    _maybe_reinit_stage(scope)
    viewer = scope_viewer_widget.ScopeViewerWidget(scope)
    viewer.show()
    focus_roi = roi_class(viewer, geometry=((400, 200), (2200, 2000)), **roi_kws)
    focus_roi.setSelected(True)
    positions = []
    rois = []

    print('Press enter after each position has been found; press control-c to end')
    while True:
        try:
            viewer.input()
        except KeyboardInterrupt:
            break
        rect = focus_roi.rect()
        if not rect.isValid():
            print('Please draw a ROI in the viewer and press enter')
            continue
        rois.append(rect)
        positions.append(scope.stage.position)
        print('Position {}: {}'.format(len(positions), tuple(positions[-1])))
    focus_roi.remove()
    viewer.close()
    return positions, rois

def write_roi_mask_files(data_dir, rois, shape='ellipse', radius=0):
    """ Create a "Focus Masks" directory of ROIs for timecourse acquisitions.

    Focus ROIs obtained from get_positions_with_roi() will be converted to mask
    images and written to "Focus Masks" in the experiment directory.

    NOTE: focus ROIs are used ONLY in fine-focus-only mode. They will be ignored
    if DO_COARSE_FOCUS is True.

    Parameters:
        data_dir: directory to write metadata file into
        rois: list of Qt.QRectFs describing the bounds of an ROI within
            which autofocus scores will be calculated, OR dict mapping different
            category names to lists of Qt.QRectFs.
        shape: 'rect' or 'ellipse'
        radius: if shape is rect, radius of corners in terms of percent of width

    """
    assert shape in {'rect', 'ellipse'}
    mask_dir = pathlib.Path(data_dir) / 'Focus Masks'
    mask_dir.mkdir(parents=True, exist_ok=True)
    image = Qt.QImage(2560, 2160, Qt.QImage.Format_Grayscale8)
    painter = Qt.QPainter()
    try:
        items = rois.items()
    except AttributeError:
        items = [('', rois)]

    for name_prefix, rois in items:
        names = _name_positions(len(rois), name_prefix)
        for name, r in zip(names, rois):
            image.fill(Qt.Qt.black)
            painter.begin(image)
            painter.setBrush(Qt.Qt.white)
            if shape == 'ellipse':
                painter.drawEllipse(r)
            elif radius > 0:
                corner = r.width() * radius
                painter.drawRoundedRect(r, corner, corner)
            else:
                painter.drawRect(r)
            painter.end()
            image.save(str(mask_dir / name)+'.png')
    del image # image must be deleted before painter to avoid warning. So delete now...

def update_z_positions(data_dir, scope):
    """Interactively update the z positions for an existing experiment.

    New positions are written to a 'z_updates' metadata dictionary, which is
    used by the acquisiton script to override the previous focal position.

    Parameters:
        data_dir: experiment directory with existing experiment_metadata.json
            file.
        scope: scope object.
    """
    data_dir = pathlib.Path(data_dir)
    experiment_metadata_path, experiment_metadata = metadata_util.get_experiment_metadata(data_dir)
    positions = experiment_metadata['positions']

    new_z = {}
    for position_name in sorted(positions.keys()):
        position_dir, metadata_path, position_metadata = metadata_util.get_position_metadata(data_dir position_name)
        scope.stage.position = metadata_util.get_latest_coordinates(position_name, experiment_metadata, position_metadata)
        input('refine position {} (press enter when done)'.format(position_name))
        new_z[position_name] = scope.stage.z

    experiment_metadata.setdefault('z_updates', {})[datetime.datetime.now().isoformat()] = new_z
    datafile.json_encode_atomic_legible_to_file(experiment_metadata, experiment_metadata_path)


def update_positions(data_dir, scope, image_type='bf', dry_run=False, ignore_autofocus_z=False):
    """Interactively update the xyz positions for an existing experiment.

    New z positions are written to a 'z_updates' metadata dictionary, which is
    used by the acquisiton script to override the previous focal position. New
    x,y positions are written directly to the experiment metadata. (The old
    positions are stored in the metadata file as "old_positions".)

    Parameters:
        data_dir: experiment directory with existing experiment_metadata.json
            file.
        scope: scope object
        dry_run: if True, don't actually write files
        ignore_autofocus_z: if True, don't use the last-autofocused z value;
            instead just use the value from the original metadata file.
    """
    data_dir = pathlib.Path(data_dir)
    experiment_metadata_path, experiment_metadata = metadata_util.get_experiment_metadata(data_dir)
    positions = experiment_metadata['positions']
    new_positions = {}
    names, xyzs = zip(*positions.items())
    old_xys = []
    new_xys = []
    rotation = numpy.eye(2)
    translation = [0, 0]
    position_order = _farthest_points(numpy.array(xyzs)[:, :2])
    viewer = scope_viewer_widget.ScopeViewerWidget(scope)
    viewer.show()
    viewer.layers.append(layer.Layer())
    viewer.layers[0].tint = 0, 1, 0 # green
    viewer.layers[1].tint = 1, 0, 1 # purple

    with scope.camera.in_state(live_mode=True), scope.tl.lamp.in_state(enabled=True), scope.stage.in_state(async_=True):
        for i in position_order:
            position_name = names[i]
            position_dir, metadata_path, position_metadata = metadata_util.get_position_metadata(data_dir position_name)
            x, y, z = metadata_util.get_latest_coordinates(position_name, experiment_metadata, position_metadata, ignore_autofocus_z)
            # now apply current guess of rotation and translation to get estimated
            # new position
            x, y = numpy.dot([x, y], rotation) + translation
            scope.stage.position = x, y, z

            image = None
            for m in position_metadata[::-1]:
                timepoint = m['timepoint']
                image_f = position_dir / f'{timepoint} {image_type}.png'
                if image_f.exists():
                    image = freeimage.read(image_f)
                    break

            scope.stage.wait()

            if image is None:
                print(f'Could not find any {image_type} image for position {position_name}; skipping')
                continue
            if len(viewer.live_image_page) == 2:
                viewer.live_image_page[1] = image
            else:
                viewer.live_image_page.append(image)

            out = viewer.input('refine position {} (press enter when done, or press "x" if the position is no longer available)'.format(position_name))
            if out.strip().lower() == 'x':
                continue
            old_xys.append(x, y)
            x, y, z = scope.stage.position
            new_positions[position_name] = x, y, z
            new_xys.append(x, y)
            rotation, _, translation, _ = fit_affine.fit_affine(old_xys, new_xys, find_scale=False, find_translation=True)
            angle = numpy.arctan2(rotation[0, 1], rotation[0, 0]) * 180 / numpy.pi
            micron_trans = translation * 1000
            print(f'\t estimated rotation angle: {angle:.1f}°')
            print(f'\t estimated translation: ({micron_trans[0]:.0f}, {micron_trans[1]:.0f}) µm')

    new_z = {position_name: z for position_name, (x, y, z) in new_positions.items()}
    experiment_metadata.setdefault('z_updates', {})[datetime.datetime.now().isoformat()] = new_z
    experiment_metadata['old_positions'] = positions
    experiment_metadata['positions'] = new_positions
    if not dry_run:
        datafile.json_encode_atomic_legible_to_file(experiment_metadata, experiment_metadata_path)

def _farthest_points(points):
    points = numpy.asarray(points)
    bbox_lower_left = points.min(axis=0)
    lower_left = numpy.linalg.norm(points - bbox_lower_left, axis=1).argmin()
    selected = [lower_left]
    dist = spatial.distance_matrix(points, points)
    for _ in range(len(points) - 1):
        dist_to_selected = dist[selected]
        dist_to_nearest_selected = dist_to_selected.min(axis=0)
        farthest_from_selected = dist_to_nearest_selected.argmax()
        selected.append(farthest_from_selected)
    return selected