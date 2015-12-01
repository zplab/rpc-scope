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
# Authors: Erik Hvatum, Zach Pincus

from . import stand
from ...messaging import message_device
from ...util import enumerated_properties

# TL and IL lamp and shutters
SET_LAMP = 77020
GET_LAMP = 77021
SET_SHUTTER_LAMP = 77032
GET_SHUTTER_LAMP = 77033
SET_SHUTTER_EVENT_SUBSCRIPTIONS = 77003
# NB: 77032 is an unusual command in that two outstanding instances issued with
# different values for their first parameter are answered separately.
# Furthermore, the response does not include any parameters, making it difficult
# (if responses are always received in order) or impossible (if they are not)
# to match response to command without retaining state information and requested
# changes to that state. If such information were kept, a failure could then be
# resolved to a specific request by comparing expected post-condition and actual
# post-condition.
# However, if we do not not coalescing the messages (see the MessageManager.send_message()
# documentation for details) we are at least guaranteed to be able
# to wait for the same number of responses as messages sent, even if we can't
# match up the precise message and responses. This should be good enough.
SET_SHUTTER_CTL = 77034
GET_SHUTTER_CTL = 77035

# filter cube positions
POS_ABS_IL_TURRET = 78022
GET_POS_IL_TURRET = 78023
GET_CUBENAME = 78027
GET_MIN_POS_IL_TURRET = 78031
GET_MAX_POS_IL_TURRET = 78032
SET_IL_TURRET_EVENT_SUBSCRIPTIONS = 78003

#swing-out condenser head
POS_ABS_KOND = 81022
GET_POS_KOND = 81023
SET_KOND_EVENT_SUBSCRIPTIONS = 81003

# TL field (LFBL) and aperture (APBL) diaphragm
POS_ABS_LFBL_TL = 83022
GET_POS_LFBL_TL = 83023
GET_MAX_POS_LFBL_TL = 83027
GET_MIN_POS_LFBL_TL = 83028
SET_LFBL_TL_EVENT_SUBSCRIPTIONS = 83003

POS_ABS_APBL_TL = 84022
GET_POS_APBL_TL = 84023
GET_MAX_POS_APBL_TL = 84027
GET_MIN_POS_APBL_TL = 84028
SET_APBL_TL_EVENT_SUBSCRIPTIONS = 84003

# IL field wheel
POS_ABS_LFWHEEL = 94022
GET_POS_LFWHEEL = 94023
GET_MAX_POS_LFWHEEL = 94027
GET_MIN_POS_LFWHEEL = 94028
GET_LFWHEEL_PROPERTIES = 94032
SET_LFWHEEL_EVENT_SUBSCRIPTIONS = 94003

from ...util import logging
logger = logging.get_logger(__name__)

class FilterCube(enumerated_properties.DictProperty):
    def __init__(self, il):
        self._il = il
        super().__init__()

    def get_value(self):
        hw_value = self._read()
        return None if hw_value == 0 else self._hw_to_usr[hw_value]

    def _get_hw_to_usr(self):
        min_pos = int(self._il.send_message(GET_MIN_POS_IL_TURRET, async=False, intent="get IL turret minimum position").response)
        max_pos = int(self._il.send_message(GET_MAX_POS_IL_TURRET, async=False, intent="get IL turret maximum position").response)
        # NB: All positions in our filter cube turret are occupied and the manual does not describe the response to
        # a name query for an empty position. I assume that it is "-" or "", but this assumption may require correction
        # if we ever do come to have an empty position.
        d = {}
        for i in range(min_pos, max_pos+1):
            name = self._il.send_message(GET_CUBENAME, i, async=False, intent="get filter cube name").response[1:].strip()
            if len(name) != 0 and name != '-':
                d[i] = name
        return d

    def _read(self):
        return int(self._il.send_message(GET_POS_IL_TURRET, async=False, intent="get filter turret position").response.split(' ')[0])

    def _write(self, value):
        self._il.send_message(POS_ABS_IL_TURRET, value, intent="set filter turret position")

class ILFieldWheel(enumerated_properties.DictProperty):
    _shape_info = {'C': 'circle', 'R': 'rectangle', '-': ''}
    def __init__(self, il):
        self._il = il
        super().__init__()

    def _get_hw_to_usr(self):
        min_pos = int(self._il.send_message(GET_MIN_POS_LFWHEEL, async=False, intent="get IL field wheel minimum position").response)
        max_pos = int(self._il.send_message(GET_MAX_POS_LFWHEEL, async=False, intent="get IL field wheel maximum position").response)
        d = {}
        for i in range(min_pos, max_pos+1):
            pos, shape, size, *special = self._il.send_message(GET_LFWHEEL_PROPERTIES, i, async=False, intent="get IL field wheel property values name").response.split(' ')

            name = '{}:{}'.format(self._shape_info[shape], size)
            if special:
                name += special[0]
            d[i] = name
        return d

    def _read(self):
        return int(self._il.send_message(GET_POS_LFWHEEL, async=False, intent="get IL field wheel position").response)

    def _write(self, value):
        self._il.send_message(POS_ABS_LFWHEEL, value, intent="set IL field wheel position")

class _ShutterDeviceMixin:
    def _setup_device(self):
        self._update_property('shutter_open', self.get_shutter_open())

    def get_shutter_open(self):
        '''True: shutter open, False: shutter closed.'''
        shutter_open = self.send_message(GET_SHUTTER_LAMP, async=False, intent="get shutter openedness").response.split(' ')[self._shutter_idx]
        shutter_open = int(shutter_open)
        if shutter_open == -1:
            raise RuntimeError('Shutter is in an invalid state.')
        return bool(shutter_open)

    def set_shutter_open(self, shutter_open):
        self.send_message(SET_SHUTTER_LAMP, self._shutter_idx, int(shutter_open), coalesce=False, intent="set shutter openedness")

class IL(stand.LeicaComponent):
    '''IL represents an interface into elements used in Incident Light (Fluorescence) mode.'''
    def _setup_device(self):
        self._filter_cube = FilterCube(self)
        self.get_filter_cube = self._filter_cube.get_value
        self.get_filter_cube_values = self._filter_cube.get_recognized_values
        self._update_property('filter_cube', self.get_filter_cube())
        self.send_message(SET_IL_TURRET_EVENT_SUBSCRIPTIONS, 1, async=False, intent="subscribe to filter cube turret position change events")
        self.register_event_callback(GET_POS_IL_TURRET, self._on_turret_pos_event)

    def set_filter_cube(self, cube):
        self._filter_cube.set_value(cube)

    def _on_turret_pos_event(self, response):
        self._update_property('filter_cube', response.response[1:].strip())

class DMi8_IL(IL):
    pass

class DM6000B_IL(_ShutterDeviceMixin, IL):
    '''IL represents an interface into elements used in Incident Light (Fluorescence) mode.'''
    _shutter_idx = 1
    # TODO(?): if needed, add DIC fine shearing
    def _setup_device(self):
        _ShutterDeviceMixin._setup_device(self)
        IL._setup_device(self)
        self._field_wheel = ILFieldWheel(self)
        self.get_field_wheel = self._field_wheel.get_value
        self.get_field_wheel_positions = self._field_wheel.get_recognized_values
        self.set_field_wheel = self._field_wheel.set_value
        self.send_message(SET_LFWHEEL_EVENT_SUBSCRIPTIONS, 0, 1, async=False, intent="subscribe to field diaphragm disk position change events")
        self.register_event_callback(GET_POS_LFWHEEL, self._on_lfwheel_position_change_event)
        self._update_property('field_wheel', self.get_field_wheel())

    def set_filter_cube(self, cube):
        self._filter_cube.set_value(cube)

    def _on_turret_pos_event(self, response):
        self._update_property('filter_cube', response.response[1:].strip())

    def _on_lfwheel_position_change_event(self, response):
        self._update_property('field_wheel', self._field_wheel._hw_to_usr[int(response.response)])

class TL(_ShutterDeviceMixin, stand.LeicaComponent):
    '''IL represents an interface into elements used in Transmitted Light (Brighftield and DIC) mode.'''
    _shutter_idx = 0

class DMi8_TL(TL):
    def get_TTL_shutter_control_enabled(self):
        return bool(int(self.send_message(GET_SHUTTER_CTL, self._shutter_idx, async=False).response.split(' ')[0]))

    def set_TTL_shutter_control_enabled(self, enabled):
        self.send_message(SET_SHUTTER_CTL, int(enabled), self._shutter_idx, async=False, intent='set TTL shutter control')

    def get_lamp_intensity(self):
        return int(self.send_message(GET_LAMP, self._shutter_idx, async=False).response.split(' ')[0])

    def set_lamp_intensity(self, intensity):
        self.send_message(SET_LAMP, int(intensity), self._shutter_idx, async=False, intent='set TL lamp intensity')

class DM6000B_TL(TL):
    '''IL represents an interface into elements used in Transmitted Light (Brighftield and DIC) mode.'''
    def _setup_device(self):
        super()._setup_device()
        self.send_message(SET_KOND_EVENT_SUBSCRIPTIONS, 1, async=False, intent="subscribe to flapping condenser flap events")
        self.register_event_callback(GET_POS_KOND, self._on_condenser_flap_event)
        self._update_property('condenser_retracted', self.get_condenser_retracted())
        self.send_message(SET_LFBL_TL_EVENT_SUBSCRIPTIONS, 0, 1, async=False, intent="subscribe to TL field diaphragm position change events")
        self.register_event_callback(GET_POS_LFBL_TL, self._on_field_diaphragm_position_change_event)
        self._update_property('field_diaphragm', self.get_field_diaphragm())
        self.send_message(SET_APBL_TL_EVENT_SUBSCRIPTIONS, 0, 1, async=False, intent="subscribe to TL aperture diaphragm position change events")
        self.register_event_callback(GET_POS_APBL_TL, self._on_aperture_diaphragm_position_change_event)
        self._update_property('aperture_diaphragm', self.get_aperture_diaphragm())

    def get_condenser_retracted(self):
        '''True: condenser head is deployed, False: condenser head is retracted.'''
        deployed = int(self.send_message(GET_POS_KOND, async=False, intent="get condenser position").response)
        if deployed == 2:
            logger.error('The condenser head is in an invalid state.')
        return not bool(deployed)

    def set_condenser_retracted(self, retracted):
        self.send_message(POS_ABS_KOND, int(not retracted), intent="set condenser position")

    def _on_condenser_flap_event(self, response):
        deployed = int(response.response)
        if deployed == 2:
            logger.error('The condenser head is in an invalid state.')
        self._update_property('condenser_retracted', not bool(deployed))

    def get_field_diaphragm(self):
        return int(self.send_message(GET_POS_LFBL_TL, async=False, intent="get field diaphragm position").response)

    def set_field_diaphragm(self, position):
        self.send_message(POS_ABS_LFBL_TL, position, intent="set field diaphragm position")

    def get_field_diaphragm_range(self):
        pos_min = int(self.send_message(GET_MIN_POS_LFBL_TL, async=False, intent="get field diaphragm min position").response)
        pos_max = int(self.send_message(GET_MAX_POS_LFBL_TL, async=False, intent="get field diaphragm max position").response)
        return pos_min, pos_max

    def _on_field_diaphragm_position_change_event(self, response):
        self._update_property('field_diaphragm', int(response.response))

    def get_aperture_diaphragm(self):
        return int(self.send_message(GET_POS_APBL_TL, async=False, intent="get aperture diaphragm position").response)

    def set_aperture_diaphragm(self, position):
        self.send_message(POS_ABS_APBL_TL, position, intent="set aperture diaphragm position")

    def _on_aperture_diaphragm_position_change_event(self, response):
        self._update_property('aperture_diaphragm', int(response.response))

    def get_aperture_diaphragm_range(self):
        pos_min = int(self.send_message(GET_MIN_POS_APBL_TL, async=False, intent="get aperture diaphragm min position").response)
        pos_max = int(self.send_message(GET_MAX_POS_APBL_TL, async=False, intent="get aperture diaphragm max position").response)
        return pos_min, pos_max

class DM6000B_ShutterWatcher(stand.LeicaComponent):
    def _setup_device(self):
        self.send_message(
            SET_SHUTTER_EVENT_SUBSCRIPTIONS,
            0, # lamp switched on/switched off
            0, # new lamp voltage
            0, # lamp switched
            0, # lamp step mode switched on/off
            1, # TL shutter open/closed
            1, # IL shutter open/closed
            async=False,
            intent="subscribe to TL and IL shutter opened/closed events"
        )
        self.register_event_callback(GET_SHUTTER_LAMP, self._on_shutter_event)

    def _on_shutter_event(self, response):
        tl_open, il_open = (bool(int(c)) for c in response.response.split())
        self._update_property('tl.shutter_open', tl_open)
        self._update_property('il.shutter_open', il_open)

class DMi8_ShutterWatcher(stand.LeicaComponent):
    def _setup_device(self):
        self.send_message(
            SET_SHUTTER_EVENT_SUBSCRIPTIONS,
            0, # lamp switched on/switched off
            1, # new lamp voltage
            0, # lamp switched
            0, # lamp step mode switched on/off
            1, # TL shutter open/closed
            0, # IL shutter open/closed
            async=False,
            intent="subscribe to TL and IL shutter opened/closed events"
        )
        self.register_event_callback(GET_SHUTTER_LAMP, self._on_shutter_event)
        self.register_event_callback(GET_LAMP, self._on_lamp_event)

    def _on_shutter_event(self, response):
        tl_open, il_open = (bool(int(c)) for c in response.response.split())
        self._update_property('tl.shutter_open', tl_open)
        # no IL shutter

    def _on_lamp_event(self, response):
        intensity, lamp = (bool(int(c)) for c in response.response.split())
        if lamp != 1:
            logger.warn('Received IL lamp event from DMi8 which has no Leica-controlled IL lamp')
        else:
            self._update_property('tl.lamp.intensity', intensity)
