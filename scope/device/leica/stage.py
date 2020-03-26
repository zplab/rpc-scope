# This code is licensed under the MIT License (see LICENSE file for details)

from . import stand

GET_CONVERSION_FACTOR_X = 72034
GET_CONVERSION_FACTOR_Y = 73034
GET_CONVERSION_FACTOR_Z = 71042
POS_ABS_X = 72022
POS_ABS_Y = 73022
POS_ABS_Z = 71022
GET_POS_X = 72023
GET_POS_Y = 73023
GET_POS_Z = 71023
POS_CONST_X = 72025
POS_CONST_Y = 73025
POS_CONST_Z = 71025
INIT_X = 72020
INIT_Y = 73020
INIT_RANGE_Z = 71044
BREAK_X = 72021
BREAK_Y = 73021
BREAK_Z = 71021
SET_SPEED_X = 72032
SET_SPEED_Y = 73032
SET_SPEED_Z = 71032
GET_SPEED_X = 72033
GET_SPEED_Y = 73033
GET_SPEED_Z = 71033
GET_SPEED_CONVERSION_FACTOR_X = 72037
GET_SPEED_CONVERSION_FACTOR_Y = 73037
GET_MIN_SPEED_X = 72035
GET_MIN_SPEED_Y = 73035
GET_MIN_SPEED_Z = 71058
GET_MAX_SPEED_X = 72036
GET_MAX_SPEED_Y = 73036
GET_MAX_SPEED_Z = 71059
SET_RAMP_Z = 71030
GET_RAMP_Z = 71031
GET_MIN_RAMP_Z = 71048
GET_MAX_RAMP_Z = 71049
SET_X_EVENT_SUBSCRIPTIONS = 72003
SET_Y_EVENT_SUBSCRIPTIONS = 73003
SET_Z_EVENT_SUBSCRIPTIONS = 71003
GET_STATUS_X = 72004
GET_STATUS_Y = 73004
GET_STATUS_Z = 71004
SET_XY_STEP_MODE = 72050
GET_XY_STEP_MODE = 72051
SET_Z_STEP_MODE = 71050
GET_Z_STEP_MODE = 71051
SET_X1_LIMIT = 72026
SET_Y1_LIMIT = 73026
SET_LOW_LIMIT = 71026
GET_X1_LIMIT = 72028
GET_Y1_LIMIT = 73028
GET_LOW_LIMIT = 71028
SET_X2_LIMIT = 72027
SET_Y2_LIMIT = 73027
SET_FOCUS = 71027
SET_UPPER_LIMIT = 71055
GET_X2_LIMIT = 72029
GET_Y2_LIMIT = 73029
GET_FOCUS = 71029
GET_UPPER_LIMIT = 71056
SET_FOCUS_LIMIT_ACTIVE = 71053
GET_FOCUS_LIMIT_ACTIVE = 71054


Z_SPEED_MM_PER_SECOND_PER_UNIT = 0.1488
Z_RAMP_MM_PER_SECOND_PER_SECOND_PER_UNIT = 1449
Z_MOVE_FUDGE_FACTOR = 0.056

class Stage(stand.LeicaComponent):
    def _setup_device(self):
        self._x_mm_per_count = float(self.send_message(GET_CONVERSION_FACTOR_X, async_=False).response) / 1000
        self._y_mm_per_count = float(self.send_message(GET_CONVERSION_FACTOR_Y, async_=False).response) / 1000
        self._z_mm_per_count = float(self.send_message(GET_CONVERSION_FACTOR_Z, async_=False).response) / 1000
        self._x_mm_per_count_second = float(self.send_message(GET_SPEED_CONVERSION_FACTOR_X, async_=False).response) / 1000
        self._y_mm_per_count_second = float(self.send_message(GET_SPEED_CONVERSION_FACTOR_Y, async_=False).response) / 1000
        self._x_speed_min = int(self.send_message(GET_MIN_SPEED_X, async_=False).response) * self._x_mm_per_count_second
        self._y_speed_min = int(self.send_message(GET_MIN_SPEED_Y, async_=False).response) * self._y_mm_per_count_second
        self._z_speed_min = int(self.send_message(GET_MIN_SPEED_Z, async_=False).response) * self._z_mm_per_count * Z_SPEED_MM_PER_SECOND_PER_UNIT
        self._x_speed_max = int(self.send_message(GET_MAX_SPEED_X, async_=False).response) * self._x_mm_per_count_second
        self._y_speed_max = int(self.send_message(GET_MAX_SPEED_Y, async_=False).response) * self._y_mm_per_count_second
        self._z_speed_max = int(self.send_message(GET_MAX_SPEED_Z, async_=False).response) * self._z_mm_per_count * Z_SPEED_MM_PER_SECOND_PER_UNIT
        self._z_ramp_min = int(self.send_message(GET_MIN_RAMP_Z, async_=False).response) * self._z_mm_per_count * Z_RAMP_MM_PER_SECOND_PER_SECOND_PER_UNIT
        self._z_ramp_max = int(self.send_message(GET_MAX_RAMP_Z, async_=False).response) * self._z_mm_per_count * Z_RAMP_MM_PER_SECOND_PER_SECOND_PER_UNIT
        self.send_message(
            SET_X_EVENT_SUBSCRIPTIONS,
            1, # X-axis started or stopped
            1, # X-INIT-endswitch reached or left
            1, # X-END-endswitch reached or left
            1, # Lower software-endswitch (X1) reached or left
            1, # Upper software-endswitch (X2) reached or left
            1, # New X-position
            1, # New XY_STEP_MODE (coarse/fine) set
            1, # Lower software endswitch (X1) changed
            1, # Upper software endswitch (X2) changed,
            async_=False
        )
        self._register_event_callback(GET_STATUS_X, self._on_status_x_event)
        self._register_event_callback(GET_POS_X, self._on_pos_x_event)
        self._register_event_callback(GET_XY_STEP_MODE, self._on_xy_step_mode_event)
        self._register_event_callback(GET_X1_LIMIT, self._on_x_low_soft_limit_event)
        self._register_event_callback(GET_X2_LIMIT, self._on_x_high_soft_limit_event)
        self._update_property('xy_fine_control', self.get_xy_fine_control())
        self._update_property('x_low_soft_limit', self.get_x_low_soft_limit())
        self._update_property('x_high_soft_limit', self.get_x_high_soft_limit())
        self._on_status_x_event(self.send_message(GET_STATUS_X, async_=False))
        self.send_message(
            SET_Y_EVENT_SUBSCRIPTIONS,
            1, # Y-axis started or stopped
            1, # Y-INIT-endswitch reached or left
            1, # Y-END- endswitch reached or left
            1, # Lower software-endswitch (Y1) reached or left
            1, # Upper software-endswitch (Y2) reached or left
            1, # New Y-position
            1, # Lower software endswitch (Y1) changed
            1, # Upper software endswitch (Y2) changed
            async_=False
        )
        self._register_event_callback(GET_STATUS_Y, self._on_status_y_event)
        self._register_event_callback(GET_POS_Y, self._on_pos_y_event)
        self._register_event_callback(GET_Y1_LIMIT, self._on_y_low_soft_limit_event)
        self._register_event_callback(GET_Y2_LIMIT, self._on_y_high_soft_limit_event)
        self._update_property('y_low_soft_limit', self.get_y_low_soft_limit())
        self._update_property('y_high_soft_limit', self.get_y_high_soft_limit())
        self._on_status_y_event(self.send_message(GET_STATUS_Y, async_=False))
        self.send_message(
            SET_Z_EVENT_SUBSCRIPTIONS,
            1, # Z-DRIVE started or stopped
            1, # Lower hardware endswitch reached or left
            1, # Upper hardware endswitch reached or left
            1, # Lower threshold reached or left
            1, # Focus position reached or left
            1, # New Z-position reached
            1, # New lower threshold set
            0, # New focus position set
            1, # New Z_STEP_MODE (coarse/fine) set
            async_=False
        )
        self._register_event_callback(GET_STATUS_Z, self._on_status_z_event)
        self._register_event_callback(GET_POS_Z, self._on_pos_z_event)
        self._register_event_callback(GET_Z_STEP_MODE, self._on_z_step_mode_event)
        self._register_event_callback(GET_LOW_LIMIT, self._on_z_low_soft_limit_event)
        self._update_property('z_fine_control', self.get_z_fine_control())
        self._update_property('z_low_soft_limit', self.get_z_low_soft_limit())
        self._update_property('z_high_soft_limit', self.get_z_high_soft_limit())
        self._on_status_z_event(self.send_message(GET_STATUS_Z, async_=False))
        x, y, z = self.get_position()
        self._update_property('x', x)
        self._update_property('y', y)
        self._update_property('z', z)

    def set_position(self, position):
        """Set (x, y) or (x, y, z) position.
        Any value may be None to indicate no motion is requested along that
        axis. Units are in mm.

        Each axis will move simultaneously to minimize transit time.
        """
        if len(position) == 2:
            x, y = position
            z = None
        else:
            x, y, z = position
        with self.in_state(async_=True):
            self.set_x(x)
            self.set_y(y)
            self.set_z(z)
            # no need to do self.wait() at end of block: it gets called implicitly!

    def _set_pos(self, value, conversion_factor, command, async_):
        if value is None: return
        counts = int(round(value / conversion_factor))
        self.send_message(command, counts, async_=async_, intent="move stage to position")

    def set_x(self, x, async_=None):
        """Set x-axis position in mm.  If a value other than None is supplied for the async_ parameter,
        this value is used in place of the stage's current async_ state for issuing the stage x-axis
        move command."""
        self._set_pos(x, self._x_mm_per_count, POS_ABS_X, async_)

    def set_y(self, y, async_=None):
        """Set y-axis position in mm.  If a value other than None is supplied for the async_ parameter,
        this value is used in place of the stage's current async_ state for issuing the stage y-axis
        move command."""
        self._set_pos(y, self._y_mm_per_count, POS_ABS_Y, async_)

    def set_z(self, z, async_=None):
        """Set z-axis position in mm.  If a value other than None is supplied for the async_ parameter,
        this value is used in place of the stage's current async_ state for issuing the stage z-axis
        move command."""
        self._set_pos(z, self._z_mm_per_count, POS_ABS_Z, async_)

    def z_from_offset(self, z, direction, offset=0.2, async_=None):
        """Set the z-axis position, first moving to a fixed offset from the z position.
        Useful to always approach a z position from above or below, for maximum repeatability.
        Direction parameter used to control whether the offset is approached from below (-1) or
        above (+1)."""
        assert direction in (1, -1)
        self.set_z(z + offset * direction, async_=True)
        self.set_z(z, async_=async_)

    def get_position(self):
        """Return (x,y,z) positionz in mm."""
        return self.get_x(), self.get_y(), self.get_z()

    def _get_pos(self, conversion_factor, command):
        counts = int(self.send_message(command, async_=False, intent="get stage position").response)
        mm = counts * conversion_factor
        return mm

    def get_x(self):
        """Get x-axis position in mm."""
        return self._get_pos(self._x_mm_per_count, GET_POS_X)

    def get_y(self):
        """Get y-axis position in mm."""
        return self._get_pos(self._y_mm_per_count, GET_POS_Y)

    def get_z(self):
        """Get z-axis position in mm."""
        return self._get_pos(self._z_mm_per_count, GET_POS_Z)

    def _on_pos_x_event(self, event):
        counts = int(event.response)
        mm = counts * self._x_mm_per_count
        self._update_property('x', mm)

    def _on_pos_y_event(self, event):
        counts = int(event.response)
        mm = counts * self._y_mm_per_count
        self._update_property('y', mm)

    def _on_pos_z_event(self, event):
        counts = int(event.response)
        mm = counts * self._z_mm_per_count
        self._update_property('z', mm)

    def _on_status_x_event(self, event):
        moving, lh, hh, ls, hs = (bool(int(v)) for v in event.response.split())
        self._update_property('moving_along_x', moving)
        self._update_property('at_x_low_hard_limit', lh)
        self._update_property('at_x_high_hard_limit', hh)
        self._update_property('at_x_low_soft_limit', ls)
        self._update_property('at_x_high_soft_limit', hs)

    def _on_status_y_event(self, event):
        moving, lh, hh, ls, hs = (bool(int(v)) for v in event.response.split())
        self._update_property('moving_along_y', moving)
        self._update_property('at_y_low_hard_limit', lh)
        self._update_property('at_y_high_hard_limit', hh)
        self._update_property('at_y_low_soft_limit', ls)
        self._update_property('at_y_high_soft_limit', hs)

    def _on_status_z_event(self, event):
        moving, lh, hh, ls, hs = (bool(int(v)) for v in event.response.split())
        self._update_property('moving_along_z', moving)
        self._update_property('at_z_low_hard_limit', lh)
        self._update_property('at_z_high_hard_limit', hh)
        self._update_property('at_z_low_soft_limit', ls)
        self._update_property('at_z_high_soft_limit', hs)

    def _set_soft_limit(self, value, conversion_factor, command):
        counts = int(round(value / conversion_factor))
        self.send_message(command, counts, async_=False, intent="set stage soft limit")

    def set_x_low_soft_limit(self, x_min):
        self._set_soft_limit(x_min, self._x_mm_per_count, SET_X1_LIMIT)

    def set_x_high_soft_limit(self, x_max):
        self._set_soft_limit(x_max, self._x_mm_per_count, SET_X2_LIMIT)

    def set_y_low_soft_limit(self, y_min):
        self._set_soft_limit(y_min, self._y_mm_per_count, SET_Y1_LIMIT)

    def set_y_high_soft_limit(self, y_max):
        self._set_soft_limit(y_max, self._y_mm_per_count, SET_Y2_LIMIT)

    def set_z_low_soft_limit(self, z_min):
        self._set_soft_limit(z_min, self._z_mm_per_count, SET_LOW_LIMIT)

    def set_z_high_soft_limit(self, z_max):
        self._set_soft_limit(z_max, self._z_mm_per_count, SET_UPPER_LIMIT)
        # All stage soft limit property_server properties are updated in response to soft limit change events issued
        # by the scope - except for max z, which we update immediately after we successfully change it
        self._update_property('z_high_soft_limit', self.get_z_high_soft_limit())

    def _get_soft_limit(self, conversion_factor, command):
        counts = int(self.send_message(command, async_=False, intent="get stage soft limit").response)
        mm = counts * conversion_factor
        return mm

    def get_x_low_soft_limit(self):
        return self._get_soft_limit(self._x_mm_per_count, GET_X1_LIMIT)

    def get_x_high_soft_limit(self):
        return self._get_soft_limit(self._x_mm_per_count, GET_X2_LIMIT)

    def get_y_low_soft_limit(self):
        return self._get_soft_limit(self._y_mm_per_count, GET_Y1_LIMIT)

    def get_y_high_soft_limit(self):
        return self._get_soft_limit(self._y_mm_per_count, GET_Y2_LIMIT)

    def get_z_low_soft_limit(self):
        return self._get_soft_limit(self._z_mm_per_count, GET_LOW_LIMIT)

    def get_z_high_soft_limit(self):
        return self._get_soft_limit(self._z_mm_per_count, GET_UPPER_LIMIT)

    def _on_x_low_soft_limit_event(self, event):
        self._update_property('x_low_soft_limit', int(event.response) * self._x_mm_per_count)

    def _on_x_high_soft_limit_event(self, event):
        self._update_property('x_high_soft_limit', int(event.response) * self._x_mm_per_count)

    def _on_y_low_soft_limit_event(self, event):
        self._update_property('y_low_soft_limit', int(event.response) * self._y_mm_per_count)

    def _on_y_high_soft_limit_event(self, event):
        self._update_property('y_high_soft_limit', int(event.response) * self._y_mm_per_count)

    def _on_z_low_soft_limit_event(self, event):
        self._update_property('z_low_soft_limit', int(event.response) * self._z_mm_per_count)

    def reset_x_high_soft_limit(self):
        self.send_message(
            SET_X2_LIMIT, -1, async_=False,
            intent="reset x soft max to maximum allowed value by sending SET_X2_LIMIT with the special argument value -1.")

    def reset_y_high_soft_limit(self):
        self.send_message(
            SET_Y2_LIMIT, -1, async_=False,
            intent="reset y soft max to maximum allowed value by sending SET_Y2_LIMIT with the special argument value -1.")

    def reset_z_high_soft_limit(self):
        # The Leica serial protocol docs indicate that the following should work, as it does for x and y.  However,
        # it does not work.
#       self.send_message(
#           SET_UPPER_LIMIT, -1, async_=False,
#           intent="reset z soft max to maximum allowed value by sending SET_UPPER_LIMIT with the special argument value -1.")
        # So, we just use a value slightly larger than the location of the hard limit.  Unlike the x and y high soft limits,
        # the z high soft limit can be set to ridiculously large values far beyond the hard limit.  Resetting to a sane value
        # not much beyond the hard limit at least offers the user some idea of the largest meaningful value.
        counts = int(round(26.00001 / self._z_mm_per_count))
        self.send_message(SET_UPPER_LIMIT, counts, async_=False, intent="reset z soft max to a position just past z hard max")
        self._update_property('z_high_soft_limit', self.get_z_high_soft_limit())

    def stop_x(self):
        """Immediately cease movement of the stage along the x axis"""
        self.send_message(BREAK_X, async_=False, intent="stop stage movement along x axis")

    def stop_y(self):
        """Immediately cease movement of the stage along the y axis"""
        self.send_message(BREAK_Y, async_=False, intent="stop stage movement along y axis")

    def stop_z(self):
        """Immediately cease movement of the stage along the z axis"""
        self.send_message(BREAK_Z, async_=False, intent="stop stage movement along z axis")

    def set_x_speed(self, speed):
        """Set the speed at which, when commanded to move to a specified position, the stage
        travels along x-axis, in mm/second"""
        assert self._x_speed_min <= speed <= self._x_speed_max
        counts = int(round(speed / self._x_mm_per_count_second))
        self.send_message(SET_SPEED_X, counts, intent="set x auto move speed")

    def set_y_speed(self, speed):
        """Set the speed at which, when commanded to move to a specified position, the stage
        travels along y-axis, in mm/second"""
        assert self._y_speed_min <= speed <= self._y_speed_max
        counts = int(round(speed / self._x_mm_per_count_second))
        self.send_message(SET_SPEED_Y, counts, intent="set y auto move speed")

    def set_z_speed(self, speed):
        """Set the speed at which, when commanded to move to a specified position, the stage
        travels along z-axis, in mm/second"""
        assert self._z_speed_min <= speed <= self._z_speed_max
        counts = int(round(speed / self._z_mm_per_count / Z_SPEED_MM_PER_SECOND_PER_UNIT))
        self.send_message(SET_SPEED_Z, counts, intent="set z auto move speed")

    def get_x_speed(self):
        """Get the speed at which, when commanded to move to a specified position, the stage
        moves along x-axis, in mm/second"""
        counts = int(self.send_message(GET_SPEED_X, async_=False, intent="get x auto move speed").response)
        return counts * self._x_mm_per_count_second

    def get_y_speed(self):
        """Get the speed at which, when commanded to move to a specified position, the stage
        moves along y-axis, in mm/second"""
        counts = int(self.send_message(GET_SPEED_Y, async_=False, intent="get y auto move speed").response)
        return counts * self._y_mm_per_count_second

    def get_z_speed(self):
        """Get the speed at which, when commanded to move to a specified position, the stage
        moves along z-axis, in mm/second"""
        counts = int(self.send_message(GET_SPEED_Z, async_=False, intent="get z auto move speed").response)
        return counts * self._z_mm_per_count * Z_SPEED_MM_PER_SECOND_PER_UNIT

    def move_along_x(self, speed):
        """Command stage to move along x-axis at the specified speed, in mm/second"""
        assert abs(speed) <= self._x_speed_max
        if abs(speed) < self._x_speed_min:
            self.stop_x()
        else:
            counts = int(round(speed / self._x_mm_per_count_second))
            self.send_message(POS_CONST_X, counts, intent="set x speed")

    def move_along_y(self, speed):
        """Command stage to move along y-axis at the specified speed, in mm/second"""
        assert abs(speed) <= self._y_speed_max
        if abs(speed) < self._y_speed_min:
            self.stop_y()
        else:
            counts = int(round(speed / self._y_mm_per_count_second))
            self.send_message(POS_CONST_Y, counts, intent="set y speed")

    def move_along_z(self, speed):
        """Command stage to move along z-axis at the specified speed, in mm/second"""
        assert abs(speed) <= self._z_speed_max
        if abs(speed) < self._z_speed_min:
            self.stop_z()
        else:
            counts = int(round(speed / self._z_mm_per_count / Z_SPEED_MM_PER_SECOND_PER_UNIT))
            self.send_message(POS_CONST_Z, counts, intent="set z speed")

    def get_x_min_speed(self):
        """The minimum value to which x_speed may be set.  Additionally, calling move_along_x with
        a value less than x_min_speed is equivalent to calling the stop_x method."""
        return self._x_speed_min

    def get_y_min_speed(self):
        """The minimum value to which y_speed may be set.  Additionally, calling move_along_y with
        a value less than y_min_speed is equivalent to calling the stop_y method."""
        return self._y_speed_min

    def get_z_min_speed(self):
        """The minimum value to which z_speed may be set.  Additionally, calling move_along_z with
        a value less than z_min_speed is equivalent to calling the stop_z method."""
        return self._z_speed_min

    def get_x_max_speed(self):
        """The maximum value with which move_along_x may be called and to which x_speed may be set"""
        return self._x_speed_max

    def get_y_max_speed(self):
        """The maximum value with which move_along_y may be called and to which y_speed may be set"""
        return self._y_speed_max

    def get_z_max_speed(self):
        """The maximum value with which move_along_z may be called and to which z_speed may be set"""
        return self._z_speed_max

    def get_x_speed_range(self):
        """Return min, max x speed values in mm/second"""
        return self._x_speed_min, self._x_speed_max

    def get_y_speed_range(self):
        """Return min, max y speed values in mm/second"""
        return self._y_speed_min, self._y_speed_max

    def get_z_speed_range(self):
        """Return min, max z speed values in mm/second"""
        return self._z_speed_min, self._z_speed_max

    def reinit(self):
        """Reinitialize all stage axes to correct for drift or "stuck" stage.

        CAUTION: Moves stage to top of z range (at position x=0, y=0). This
        could crash the objective if there is any obstruction."""
        self.reinit_x()
        self.reinit_y()
        self.reinit_z()

    def reinit_x(self):
        """Reinitialize x axis to correct for drift or "stuck" stage. Executes synchronously."""
        self.send_message(INIT_X, async_=False, intent="init stage x axis")

    def reinit_y(self):
        """Reinitialize y axis to correct for drift or "stuck" stage. Executes synchronously."""
        self.send_message(INIT_Y, async_=False, intent="init stage y axis")

    def reinit_z(self):
        """Reinitialize z axis to correct for drift or "stuck" stage. Executes synchronously.

        CAUTION: Moves stage to top of z range, which could crash the objective if
        there is any obstruction at the current position."""
        self.send_message(INIT_RANGE_Z, async_=False, intent="init stage z axis")
        # now back off from the z position that the stage is left in, which is
        # the closest to the objective (dangerous!)
        self.set_z(self.get_z()- 5)

    def set_xy_fine_control(self, fine):
        self.send_message(SET_XY_STEP_MODE, int(not fine), async_=False)

    def set_z_fine_control(self, fine):
        self.send_message(SET_Z_STEP_MODE, int(not fine), async_=False)

    def get_xy_fine_control(self):
        return not bool(int(self.send_message(GET_XY_STEP_MODE, async_=False).response))

    def get_z_fine_control(self):
        return not bool(int(self.send_message(GET_Z_STEP_MODE, async_=False).response))

    def _on_xy_step_mode_event(self, response):
        self._update_property('xy_fine_control', not bool(int(response.response)))

    def _on_z_step_mode_event(self, response):
        self._update_property('z_fine_control', not bool(int(response.response)))

    def get_z_ramp_range(self):
        """Return min, max z ramp values in mm/second^2"""
        return self._z_ramp_min, self._z_ramp_max

    def get_z_ramp(self):
        """Get z-axis ramp in mm/second^2"""
        counts = int(self.send_message(GET_RAMP_Z, async_=False, intent="get z ramp").response)
        return counts * self._z_mm_per_count * Z_RAMP_MM_PER_SECOND_PER_SECOND_PER_UNIT

    def set_z_ramp(self, ramp):
        """Get z-axis ramp in mm/second^2"""
        assert self._z_ramp_min <= ramp <= self._z_ramp_max
        counts = int(round(ramp / self._z_mm_per_count / Z_RAMP_MM_PER_SECOND_PER_SECOND_PER_UNIT))
        self.send_message(SET_RAMP_Z, counts, intent="set z ramp")

    def calculate_z_movement_time(self, distance):
        """Calculate how long it will take the stage to move a given z distance (in mm)
        with the current speed and ramp settings. Distance must be positive."""
        final_speed = self.get_z_speed()
        speed_ramp = self.get_z_ramp()
        # Calculate time for a movement with a simple linear acceleration ramp to a
        # final velocity, and a ramp back down so that speed=0 at the given distance.
        # Also include a "fudge factor" which is a constant amount of time for ANY move.
        #
        # Case 1: there's enough time for the stage to reach it's final speed:
        # ramp_time = final_speed / speed_ramp   # time for acceleration
        # ramp_distance = 0.5 * speed_ramp * ramp_time**2   # distance traveled
        # ramp_distance = 0.5 * final_speed**2 / speed_ramp   # simplified from above
        # total_ramp_distance = final_speed**2 / speed_ramp   # distance for speed-up and speed-down ramps
        # total_ramp_time = 2 * ramp_time   # time for speed-up and speed-down ramps
        # non_ramp_distance = distance - total_ramp_distance   # remaining distance to cover after ramps accounted for
        # NB: the rest only works if non_ramp_distance >= 0, obviously
        # non_ramp_time = non_ramp_distance / final_speed   # time to cover distance at final_speed
        # non_ramp_time = (distance - final_speed**2 / speed_ramp) / final_speed   # combined above formulae
        # non_ramp_time = distance / final_speed - final_speed / speed_ramp   # simplified
        # time = total_ramp_time + non_ramp_time   # total time is time accelerating + time cruising
        # time = 2 * final_speed / speed_ramp + distance / final_speed - final_speed / speed_ramp   # combining above
        # time = final_speed / speed_ramp + distance / final_speed   # simplified
        # NB: criterion above for case 1 can be restated as:
        # distance >= total_ramp_distance
        # distance >= final_speed**2 / speed_ramp   # simplified
        #
        # Case 2: the stage never reaches the final speed, so it just ramps up half the time
        # and down the other half.
        # ramp_distance = 0.5 * distance   # half the distance is acceleration
        # 0.5 * distance = 0.5 * speed_ramp * ramp_time**2   # ramp_distance is just acceleration formula
        # ramp_time = sqrt(distance / speed_ramp)   # solve for ramp_time
        # time = 2 * ramp_time   # got to acclerate and decelerate
        # time = 2 * sqrt(distance / speed_ramp)
        # Note that at the critical distance of final_speed**2 / speed_ramp
        # the two time formulae give equivalent values, as expected.

        if distance >= final_speed**2 / speed_ramp:
            return final_speed / speed_ramp + distance / final_speed + Z_MOVE_FUDGE_FACTOR
        else:
            return 2*(distance / speed_ramp)**2 + Z_MOVE_FUDGE_FACTOR

    def calculate_required_z_speed(self, distance, time):
        """Calculate how the speed needed for the stage to move the desired z distance
        in the specified time, using the current speed ramp, or the max valid speed if
        the required speed would be too large.

        If the distance is short enough that the stage would never get to speed,
        return the min valid speed.
        """
        speed_ramp = self.get_z_ramp()
        min_speed, max_speed = self.get_z_speed_range()
        # case 1 above:
        # time = final_speed / speed_ramp + distance / final_speed + fudge
        # time - fudge = (final_speed**2 + speed_ramp*distance) / (final_speed * speed_ramp)
        # (time - fudge) * final_speed * speed_ramp = final_speed**2 + speed_ramp*distance
        # 0 = final_speed**2 - (time - fudge) * final_speed * speed_ramp + speed_ramp * distance
        # 0 = v**2 + Bv + C, where B = (fudge-time)*speed_ramp and C = speed_ramp*distance
        # v = -B +- sqrt(B**2-4C)/2
        B = (Z_MOVE_FUDGE_FACTOR - time)*speed_ramp
        C = speed_ramp * distance
        discriminant = B**2-4*C
        if discriminant > 0:
            v1 = (-B + discriminant**0.5)/2
            v2 = (-B - discriminant**0.5)/2
            v1_valid = v1 > 0 and distance >= v1**2 / speed_ramp # it appears that v1 will never be valid, but I haven't worked this out in closed form...
            v2_valid = v2 > 0 and distance >= v2**2 / speed_ramp
            if v1_valid and v2_valid:
                return min(min(v1, v2), max_speed)
            elif v1_valid:
                return min(v1, max_speed)
            elif v2_valid:
                return min(v2, max_speed)
            else: # we must have a sufficient ramp that we can never go slow enough
                return min_speed
        else: # ramp and distance must be such that we can never go fast enough
            return max_speed

    def calculate_z_movement_position(self, distance, t):
        """Calculate where the stage will be (relative to the starting position)
        for a z-move of a given distance (in mm) after t seconds have elapsed.
        Distance must be positive."""
        final_speed = self.get_z_speed()
        speed_ramp = self.get_z_ramp()
        # Assume fudge is in the initial speedup and slowdown evenly
        half_fudge = Z_MOVE_FUDGE_FACTOR / 2
        if distance >= final_speed**2 / speed_ramp: # ramp up, cruise, back down
            ramp_time = final_speed / speed_ramp
            if t <= ramp_time:
                return 0.5 * speed_ramp * t**2 + half_fudge * t/ramp_time # assign first half of fudge linearly
            non_ramp_time = distance / final_speed - ramp_time
            if t <= ramp_time + non_ramp_time:
                return (0.5 * speed_ramp * ramp_time**2
                       + final_speed * (t-ramp_time)
                       + half_fudge)
            total_time = 2*ramp_time + non_ramp_time
            if t > total_time:
                t = total_time
            return (0.5 * speed_ramp * ramp_time**2
                   + final_speed * non_ramp_time
                   + 0.5 * speed_ramp * (t - ramp_time - non_ramp_time)**2
                   + half_fudge + half_fudge * (t - ramp_time - non_ramp_time) / ramp_time) # assign the second half of the fudge linearly
        else: # ramp up and down only
            ramp_time = (distance / speed_ramp)**2
            if t < ramp_time:
                return 0.5 * speed_ramp * t**2
            if t > 2 * ramp_time:
                t = 2 * ramp_time
            return ( 0.5 * speed_ramp * ramp_time**2
                   + 0.5 * speed_ramp * (ramp_time-t)**2 )

    def _generate_speed_coefficients(self):
        import time
        import numpy
        times = []
        distances = []
        speeds = []
        ramps = []
        vmin, vmax = self.get_z_speed_range()
        rmin, rmax = self.get_z_ramp_range()
        z0 = self.get_z()
        for speed in numpy.linspace(vmax/25, vmax/1.5, 8):
            for ramp in numpy.linspace(rmax/80, rmax, 8):
                threshold = speed**2/ramp
                lt = numpy.log10(threshold)
                test_distances = numpy.logspace(lt-3, lt+2, 20, base=10)
                good_distances = (test_distances > 0.001) & (test_distances < 7)
                test_distances = test_distances[good_distances]
                if len(test_distances) > 12:
                    test_distances = test_distances[::2]
                print(speed, ramp, test_distances)
                def time_move_to(z, d):
                    t0 = time.time()
                    self.set_z(z)
                    times.append(time.time()-t0)
                    distances.append(d)
                    speeds.append(speed)
                    ramps.append(ramp)
                with self.in_state(z_speed=speed, z_ramp=ramp, async_=False):
                    for d in test_distances:
                        time_move_to(z0 - d, d)
                        time_move_to(z0, d)
        times = numpy.array(times)
        distances = numpy.array(distances)
        speeds = numpy.array(speeds)
        ramps = numpy.array(ramps)
        _calibrate_z_speed_coefficients(times, distances, speeds, ramps)
        self._setup_device()
        return times, distances, speeds, ramps

def _calibrate_z_speed_coefficients(times, distances, speeds, ramps):
    import numpy

    # Need to recalculate the speed and ramp conversion factors to get to human units
    # If distance is above (final_speed * speed_factor)**2 / (speed_ramp * ramp_factor) + fudge_factor, then
    # time = (final_speed * speed_factor) / (speed_ramp * ramp_factor) + distance / (final_speed * speed_factor) + fudge_factor
    # Since time, distance, final_speed, and speed_ramp are known, we have t = (v/a) * A + (d/v) * B + C
    # where t, d, v, and a are time, distance, final_speed, and speed_ramp
    # and A = speed_factor / ramp_factor, B = 1/speed_factor, and C = fudge_factor
    # So speed_factor = 1/B and ramp_factor = 1/(AB)
    #
    # If distance is below (final_speed * speed_factor)**2 / (speed_ramp * ramp_factor) + fudge_factor, then
    # time = 2 * sqrt(distance / (speed_ramp*ramp_factor)) + fudge_factor
    # t = 1/sqrt(ramp_factor) * 2*sqrt(distance/speed_ramp) + fudge_factor
    # t = A*sqrt(d/a) + B
    # where A = 2/sqrt(ramp_factor) and b = fudge_factor
    # so ramp_factor = (2/A)**2

    speed_factor = 1
    ramp_factor = 1
    fudge_factor = 0
    for _ in range(10):
        # Using our current best guess for the distance threshold (based on
        # our estimates of acceleration and speed), update our estimates of
        # acceleration and speed using the data above the distance threshold.
        # Iterate this a few times. Hopefully it converges...
        thresholds = (speeds * speed_factor)**2 / (ramps * ramp_factor) + fudge_factor
        above_threshold = distances >= thresholds
        print(len(speeds), above_threshold.sum())
        # above threshold: t = (v/a) * A + (d/v) * B + C
        # A = speed_factor / ramp_factor, B = 1/speed_factor, and C = fudge_factor
        t, d, v, a = times[above_threshold], distances[above_threshold], speeds[above_threshold], ramps[above_threshold]
        ones = numpy.ones_like(t)
        (A, B, C), resid, rank, s = numpy.linalg.lstsq(numpy.transpose([v/a, d/v, ones]), t)
        print(resid.mean())
        speed_factor = 1/B
        ramp_factor = 1/(A*B)
        fudge_factor = C
        print(speed_factor, ramp_factor, fudge_factor)
        # below_threshold: t = A*sqrt(d/a) + B
        # A = 2/sqrt(ramp_factor) and b = fudge_factor
        t, d, a = times[~above_threshold], distances[~above_threshold], ramps[~above_threshold]
        if len(t) > 0:
            ones = numpy.ones_like(t)
            (A, B), resid, rank, s = numpy.linalg.lstsq(numpy.transpose([(d/a)**0.5, ones]), t)
            alt_ramp_factor = (2/A)**2
            alt_fudge_factor = B
            print(alt_ramp_factor, alt_fudge_factor)
    time_estimates = numpy.empty_like(times)
    time_estimates[~above_threshold] = 2 * (distances[~above_threshold] / (ramps[~above_threshold]*ramp_factor))**0.5 + fudge_factor
    time_estimates[above_threshold] = speeds[above_threshold]*speed_factor / (ramps[above_threshold]*ramp_factor) + \
        distances[above_threshold] / (speeds[above_threshold]*speed_factor) + fudge_factor

    global Z_SPEED_MM_PER_SECOND_PER_UNIT, Z_RAMP_MM_PER_SECOND_PER_SECOND_PER_UNIT, Z_MOVE_FUDGE_FACTOR
    Z_SPEED_MM_PER_SECOND_PER_UNIT *= speed_factor
    Z_RAMP_MM_PER_SECOND_PER_SECOND_PER_UNIT *= ramp_factor
    Z_MOVE_FUDGE_FACTOR = fudge_factor
    return time_estimates
