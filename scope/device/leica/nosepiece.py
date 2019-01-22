# This code is licensed under the MIT License (see LICENSE file for details)

import collections

from ...messaging import message_device
from . import stand
from . import microscopy_method_names

POS_ABS_OBJ = 76022
GET_POS_OBJ = 76023
SET_MODE = 76025
GET_MODE = 76026
SET_IMM_DRY = 76027
GET_IMM_DRY = 76028
SET_OBJPAR = 76032
GET_OBJPAR = 76033
GET_MIN_POS_OBJ = 76038
GET_MAX_POS_OBJ = 76039
SET_OBJECTIVE_TURRET_EVENT_SUBSCRIPTIONS = 76003

class ManualNosepiece(stand.LeicaComponent):
    # Note that objective position is reported as 0 when the objective turret is between positions. The objective
    # turret is between positions when it is in the process of responding to a position change request and also when
    # manually placed there by physical intervention.

    def _setup_device(self):
        self._minp = int(self.send_message(GET_MIN_POS_OBJ, async_=False, intent="get minimum objective turret position").response)
        self._maxp = int(self.send_message(GET_MAX_POS_OBJ, async_=False, intent="get maximum objective turret position").response)
        self._mags = [None for i in range(self._maxp + 1)]
        self._mags_to_positions = collections.defaultdict(list)
        for p in range(self._minp, self._maxp+1):
            mag = self.send_message(GET_OBJPAR, p, 1).response.split(' ')[2]
            # Note: dm6000b reports magnifications in integer units with a dash indicating no magnification / empty
            # turret position
            mag = None if mag == '-' else int(mag)
            self._mags[p] = mag
            self._mags_to_positions[mag].append(p)

        # Ensure that halogen variable spectra correction filter is always set to maximum (least attenuation)
        # NB: does nothing on stands with no correction filter (DMi8, maybe DM6?).
        self._set_objectives_intensities(255)

        self.send_message(SET_OBJECTIVE_TURRET_EVENT_SUBSCRIPTIONS, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, async_=False, intent="subscribe to objective turret position change events")
        self._register_event_callback(GET_OBJPAR, self._on_turret_moved_event)
        self._update_property('position', self.get_position())

    def get_position(self):
        '''Current objective turret position. Note that 0 is special and indicates that the objective turret is
        between objective positions.'''
        return int(self.send_message(GET_POS_OBJ, async_=False, intent="get current objective turret position").response)

    def get_position_min_max(self):
        return self._minp, self._maxp

    def get_magnification(self):
        '''The current objective's magnification. I.e., the magnification of the objective at the currently selected
        objective turret position. Note that if the objective turret is between positions or is set to an empty position,
        this value will be None.'''
        mag = self._get_objpar(self.get_position(), 1)
        if mag == '-':
            return None
        else:
            return int(mag)

    def get_magnification_values(self):
        return list(sorted(filter(lambda m: m is not None, self._mags_to_positions.keys())))


    def get_immersion_mode(self):
        '''True if the microscope is in immersion mode.'''
        return self.send_message(GET_IMM_DRY, async_=False, intent="get current objective medium").response == 'I'

    def set_immersion_mode(self, immersion):
        '''If set to True, the microscope will be set to immersion mode.'''
        if immersion:
            medium = 'I'
        else:
            medium = 'D'
        self.send_message(SET_IMM_DRY, medium, intent="change to objective medium")

    def get_all_objectives(self):
        '''Returns a list of objective magnifications. List index corresponds to objective position. None values
        in the list represent empty objective turret positions. For example, [None, 10, 5] indicates that there
        is no objective at position 0, a 10x objective at position 1, and a 5x objective at objective turret position
        2.

        Note that position 0 always has no objective, as it is the special signal for "between positions".
        '''
        return self._mags

    def _on_turret_moved_event(self, response):
        self._update_property('position', int(response.response.split()[0]))

    def _get_objpar(self, obj_pos, objpar_idx):
        param = self.send_message(GET_OBJPAR, obj_pos, objpar_idx, async_=False).response.split(' ')[2:]
        if len(param) == 1:
            return param[0]
        else:
            return param

    _PER_METHOD_PROPERTIES = ((10, 'illumination field diaphragm value TL'),
                              (11, 'aperture diaphragm value TL'),
                              (12, 'illumination field diaphragm value IL'),
                              (13, 'aperture diaphragm value IL'),
                              (14, 'lamp intensity'),
                              (15, 'condenser turret position'),
                              (16, 'DIC turret position'),
                              (17, 'DIC turret fine position'))

    def get_objectives_details(self):
        '''Returns a list of objective parameter dicts / None values. List index corresponds to objective position. None values
        in the list represent empty objective turret positions. Querying this property causes internal scope components to audibly
        do things. It is therefore advisable to avoid querying this property from a script that runs regularly.'''
        objectives = [None for i in range(self._maxp + 1)]
        for p in range(self._minp, self._maxp+1):
            mag = self._get_objpar(p, 1)
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
                    'x paracentric correction': int(self._get_objpar(p, 20)),
                    'y paracentric correction': int(self._get_objpar(p, 21))
                }
                try:
                    details['z lowering flag'] = bool(int(self._get_objpar(p, 19)))
                except message_device.LeicaError:
                    pass
                for objpar_idx, objpar_name in self._PER_METHOD_PROPERTIES:
                    meth_objpars = reversed(self._get_objpar(p, objpar_idx))
                    details[objpar_name] = {microscopy_method_names.NAMES[meth_idx]: int(meth_objpar)
                                                 for meth_idx, meth_objpar in enumerate(meth_objpars)}
                method_mask = reversed(list(self._get_objpar(p, 1)))
                details['microscopy methods'] = [microscopy_method_names.NAMES[meth_idx] for meth_idx, v in enumerate(method_mask) if bool(int(v))]
                objectives[p] = details
        return objectives

    def _set_objectives_intensities(self, intensity):
        intensities = ' '.join([str(intensity)] * 16)
        for p in range(self._minp, self._maxp+1):
            self.send_message(SET_OBJPAR, p, 14, intensities, async_=False, intent="set per-microscopy-mode objective intensities")


class MotorizedNosepiece(ManualNosepiece):
    def set_position(self, position):
        if position == 0:
            raise ValueError('Nosepiece position can not be set to 0; zero indicates that the nosepiece is currently between objective positions.')
        if not (self._minp <= position <= self._maxp):
            raise ValueError('Nosepiece position must be in range [{}, {}].'.format(self._minp, self._maxp))
        self.send_message(POS_ABS_OBJ, position, intent="change objective turret position")

    def set_magnification(self, magnification):
        if magnification not in self._mags_to_positions:
            raise ValueError('magnification must be one of the following: {}.'.format(sorted([m for m in list(self._mags_to_positions.keys()) if m is not None])))
        mag_positions = self._mags_to_positions[magnification]
        if len(mag_positions) > 1:
            raise ValueError('magnification value {} is ambiguous; objectives at positions {} all have this magnification.'.format(magnification, mag_positions))
        self.send_message(POS_ABS_OBJ, mag_positions[0], intent="change objective turret position")


class MotorizedNosepieceWithSafeMode(MotorizedNosepiece):
    def set_position(self, position):
        try:
            super().set_position(position)
        except stand.message_device.LeicaError:
            if self.get_safe_mode() and self._get_objpar(self.get_position(), 5) != self._get_objpar(position, 5):
                raise stand.message_device.LeicaError('Attempting to change to an objective with a different immersion/dry state is forbidden in safe mode.')
            else:
                raise

    def get_safe_mode(self):
        '''True if the microscope must be explicitly set to "dry" or "immersion" mode before changing to
        a dry or immersion lens.'''
        return self.send_message(GET_MODE, async_=False, intent="get objective turret mode").response == '1'

    def set_safe_mode(self, mode):
        '''If set to True, the microscope must be explicitly set to "dry" or "immersion" mode before changing to
        a dry or immersion lens.'''
        leica_mode = 1 if mode else 0
        self.send_message(SET_MODE, leica_mode, intent="set objective turret mode")

