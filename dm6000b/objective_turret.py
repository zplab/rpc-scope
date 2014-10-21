# The MIT License (MIT)
#
# Copyright (c) 2014 WUSTL ZPLAB
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
# Authors: Erik Hvatum, Zach Pincus

from rpc_acquisition import message_device
from rpc_acquisition.dm6000b import microscopy_method_names

POS_ABS_OBJ = 76022
GET_POS_OBJ = 76023
SET_IMM_DRY = 76027
GET_IMM_DRY = 76028
SET_OBJPAR = 76032
GET_OBJPAR = 76033
GET_MIN_POS_OBJ = 76038
GET_MAX_POS_OBJ = 76039

class ObjectiveTurret(message_device.LeicaAsyncDevice):
    '''Note that objective position is reported as 0 when the objective turret is between positions.  The objective
    turret is between positions when it is in the process of responding to a position change request and also when
    manually placed there by physical intervention.'''
    def _setup_device(self):
        self._minp = int(self.send_message(GET_MIN_POS_OBJ, async=False, intent="get minimum objective turret position").response)
        self._maxp = int(self.send_message(GET_MAX_POS_OBJ, async=False, intent="get maximum objective turret position").response)
        self._mags = [None for i in range(self._maxp + 1)]
        self._mags_to_positions = {}
        for p in range(self._minp, self._maxp+1):
            mag = self.send_message(GET_OBJPAR, p, 1).response.split(' ')[2]
            # Note: dm6000b reports magnifications in integer units with a dash indicating no magnification / empty
            # turret position
            mag = None if mag == '-' else int(mag)
            self._mags[p] = mag
            if mag not in self._mags_to_positions:
                self._mags_to_positions[mag] = [p]
            else:
                self._mags_to_positions[mag].append(p)

        # Ensure that halogen variable spectra correction filter is always set to maximum (least attenuation)
        self._set_objectives_intensities(255)

    def set_position(self, position):
        if position is not None:
            response = self.send_message(POS_ABS_OBJ, position, intent="change objective turret position")

    def get_position(self):
        '''Current objective turret position.  Note that 0 is special and indicates that the objective turret is
        between objective positions.'''
        return int(self.send_message(GET_POS_OBJ, async=False, intent="get current objective turret position").response)

    def get_position_min_max(self):
        return self._minp, self._maxp

    def set_magnification(self, magnification):
        if magnification not in self._mags_to_positions:
            raise ValueError('magnification must be one of the following: {}.'.format(sorted([m for m in list(self._mags_to_positions.keys()) if m is not None])))
        mag_positions = self._mags_to_positions[magnification]
        if len(mag_positions) > 1:
            raise ValueError('magnification value {} is ambiguous; objectives at positions {} all have this magnification.'.format(magnification, mag_positions))
        response = self.send_message(POS_ABS_OBJ, mag_positions[0], intent="change objective turret position")

    def get_magnification(self):
        '''The current objective's magnification.  I.e., the magnification of the objective at the currently selected
        objective turret position.  Note that if the objective turret is between positions or is set to an empty position,
        this value will be None.'''
        mag = self.send_message(GET_OBJPAR, self.get_position(), 1, async=False, intent="get magnification of objective at current position").response.split(' ')[2]
        if mag == '-':
            return None
        else:
            return int(mag)

    def get_immersion_or_dry(self):
        '''Returns 'I' or 'D' depending on whether the dm6000b is in immersion or dry mode.  Setting this property to 'T'
        causes the dm6000b to toggle between 'I' and 'D'.'''
        return self.send_message(GET_IMM_DRY, async=False, intent="get current objective medium").response

    def set_immersion_or_dry(self, medium):
        response = self.send_message(SET_IMM_DRY, medium, intent="change to objective medium")

    def get_all_objectives(self):
        '''Returns a list of objective magnifications.  List index corresponds to objective position.  None values
        in the list represent empty objective turret positions.  For example, [None, 10, 5] indicates that there 
        is no objective at position 0, a 10x objective at position 1, and a 5x objective at objective turret position
        2.'''
        return self._mags

    def _get_objpar(self, obj_pos, objpar_idx):
        param = self.send_message(GET_OBJPAR, p, 2, async=False).response.split(' ')[2:]
        if len(param) == 1:
            return param[0]
        else:
            return param
    
    PER_METHOD_PROPERTIES = ((10, 'illumination field diaphragm value TL'),
                             (11, 'aperture diaphragm value TL'),
                             (12, 'illumination field diaphragm value IL'),
                             (13, 'aperture diaphragm value IL'),
                             (14, 'lamp intensity'),
                             (15, 'condenser turret position'),
                             (16, 'DIC turret position'),
                             (17, 'DIC turret fine position'))
    
    def get_objectives_details(self):
        '''Returns a list of objective parameter dicts / None values.  List index corresponds to objective position.  None values
        in the list represent empty objective turret positions.  Querying this property causes internal scope components to audibly
        do things.  It is therefore advisable to avoid querying this property from a script that runs regularly.'''
        objectives = [None for i in range(self._maxp + 1)]
        for p in range(self._minp, self._maxp+1):
            mag = self.send_message(GET_OBJPAR, p, 1).response.split(' ')[2]
            if mag != '-':
                details = {
                    'magnification': int(mag),
                    'numerical aperture': float(self._get_objpar(p, 2)),
                    'article number': int(self._get_objpar(p, 3)),
                    'type': self._get_objpar(p, 5),
                    'parfocality leveling': int(self._get_objpar(p, 6)),
                    'lower z': int(self._get_objpar(p, 7)),
                    'immerse z': int(self._get_objpar(p, 8)),
                    'z step increment': int(self._get_objpar(p, 9)),
                    'z lowering flag': bool(int(self._get_objpar(p, 19))),
                    'x paracentric correction': int(self._get_objpar(p, 20)),
                    'y paracentric correction': int(self._get_objpar(p, 21))
                }
                for objpar_idx, objpar_name in self.PER_METHOD_PROPERTIES:
                    meth_objpars = reversed(self._get_objpar(p, objpar_idx))
                    details[objpar_name] = { microscopy_method_names.NAMES[meth_idx]: int(meth_objpar) 
                                                 for meth_idx, meth_objpar in enumerate(meth_objpars)}
                method_mask = list(self.send_message(GET_OBJPAR, p, 4, async=False).response.split(' ')[2])
                method_mask.reverse()
                details['microscopy methods'] = [microscopy_method_names.NAMES[meth_idx] for meth_idx, v in enumerate(method_mask) if bool(int(v))]
                objectives[p] = details
        return objectives

    def _set_objectives_intensities(self, intensity):
        intensities = ' '.join([str(intensity)] * 16)
        for p in range(self._minp, self._maxp+1):
            self.send_message(SET_OBJPAR, p, 14, intensities, async=False, intent="set per-microscopy-mode objective intensities")
