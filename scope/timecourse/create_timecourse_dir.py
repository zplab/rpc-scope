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

import string
import pathlib
import math

from ..util import json_encode

handler_template = string.Template(
"""from scope.timecourse import timecourse_handler

class Handler(timecourse_handler.BasicAcquisitionHandler):
    FILTER_CUBE = $filter_cube
    FLUORESCENCE_FLATFIELD_LAMP = $fl_flatfield_lamp
    RUN_INTERVAL_MINUTES = $run_interval
    OBJECTIVE = 10
    PIXEL_READOUT_RATE = '100 MHz'
    USE_LAST_FOCUS_POSITION = True

    def configure_additional_acquisition_steps(self):
        pass

if __name__ == '__main__':
    Handler.main()
""")

def create_timecourse_dir(data_dir, positions, z_max, reference_positions, run_interval,
    filter_cube, fluorescence_flatfield_lamp=None):
    """
    Parameters:
        data_dir: directory to write python and config files to
        positions: list of (x,y,z) positions, OR dict mapping different category
            names to lists of (x,y,z) positions.
        z_max: maximum z-value allowed during autofocus
        reference_positions: list of (x,y,z) positions to be used to generate
            brightfield and optionally fluorescence flat-field images.
        run_interval: desired number of minutes between starts of timepoint
            acquisitions.
        filter_cube: name of the filter cube to use
        fluorescence_flatfield_lamp: if fluorescent flatfield images are
            desired, provide the name of an appropriate spectra x lamp that is
            compatible with the specified filter cube.
    """
    data_dir = pathlib.Path(data_dir)
    if not data_dir.exists():
        data_dir.mkdir()
    code = handler_template.substitute(filter_cube=filter_cube,
        fl_flatfield_lamp=fluorescence_flatfield_lamp, run_interval=run_interval)
    with (data_dir / 'acquire.py').open('w') as f:
        f.write(code)
    try:
        items = positions.items()
    except AttributeError:
        items = [('', positions)]
    named_positions = {}
    for name_prefix, positions in items:
        names = _name_positions(len(positions), name_prefix)
        named_positions.update(zip(names, positions))
    metadata = dict(z_max=z_max, reference_positions=reference_positions,
        positions=named_positions)
    with (data_dir / 'experiment_metadata.json').open('w') as f:
        json_encode.encode_legible_to_file(metadata, f)

def simple_get_positions(scope):
    """Return a list of interactively-obtained scope stage positions."""
    positions = []
    print('Press enter after each position has been found; press control-c to end')
    while True:
        try:
            input()
        except KeyboardInterrupt:
            break
        positions.append(scope.stage.position)
        print('Position {} recorded as {}.'.format(len(positions), tuple(position)), end='')
    return positions

def _name_positions(num_positions, name_prefix):
    padding = int(math.ceil(math.log10(max(1, num_positions-1))))
    names = ['{}{:0{pad}}'.format(name_prefix, i, pad=padding) for i in range(num_positions)]
    return names