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
# Authors: Zach Pincus, Erik Hvatum

from . import stand
from ...util import state_stack

GET_CONVERSION_FACTOR_X = 72034
GET_CONVERSION_FACTOR_Y = 73034
GET_CONVERSION_FACTOR_Z = 71042
POS_ABS_X = 72022
POS_ABS_Y = 73022
POS_ABS_Z = 71022
GET_POS_X = 72023
GET_POS_Y = 73023
GET_POS_Z = 71023
INIT_X = 72020
INIT_Y = 73020
INIT_RANGE_Z = 71044
SET_SPEED_Z = 71032
GET_SPEED_Z = 71033
GET_MIN_SPEED_Z = 71058
GET_MAX_SPEED_Z = 71059
SET_RAMP_Z = 71030
GET_RAMP_Z = 71031
GET_MIN_RAMP_Z = 71048
GET_MAX_RAMP_Z = 71049


Z_SPEED_MM_PER_SECOND_PER_UNIT = 0.1488
Z_RAMP_MM_PER_SECOND_PER_SECOND_PER_UNIT = 1449
Z_MOVE_FUDGE_FACTOR = 0.056

class Stage(stand.DM6000Device):
    def _setup_device(self):
        self._x_mm_per_count = float(self.send_message(GET_CONVERSION_FACTOR_X, async=False).response) / 1000
        self._y_mm_per_count = float(self.send_message(GET_CONVERSION_FACTOR_Y, async=False).response) / 1000
        self._z_mm_per_count = float(self.send_message(GET_CONVERSION_FACTOR_Z, async=False).response) / 1000
        self._z_speed_min = int(self.send_message(GET_MIN_SPEED_Z, async=False).response) * self._z_mm_per_count * Z_SPEED_MM_PER_SECOND_PER_UNIT
        self._z_speed_max = int(self.send_message(GET_MAX_SPEED_Z, async=False).response) * self._z_mm_per_count * Z_SPEED_MM_PER_SECOND_PER_UNIT
        self._z_ramp_min = int(self.send_message(GET_MIN_RAMP_Z, async=False).response) * self._z_mm_per_count * Z_RAMP_MM_PER_SECOND_PER_SECOND_PER_UNIT
        self._z_ramp_max = int(self.send_message(GET_MAX_RAMP_Z, async=False).response) * self._z_mm_per_count * Z_RAMP_MM_PER_SECOND_PER_SECOND_PER_UNIT

        x, y, z = self.get_position()
        self._update_property('x', x)
        self._update_property('y', y)
        self._update_property('z', z)

    def set_position(self, xyz):
        """Set x, y, and z position to respective elements of xyz tuple/iterable.
        Any may be None to indicate no motion is requested. Units are in mm."""
        x, y, z = xyz
        self.set_x(x)
        self.set_y(y)
        self.set_z(z)

    def _set_pos(self, value, conversion_factor, command):
        if value is None: return
        counts = int(round(value / conversion_factor))
        response = self.send_message(command, counts, intent="move stage to position")

    def set_x(self, x):
        "Set x-axis position in mm"
        self._set_pos(x, self._x_mm_per_count, POS_ABS_X)
        self._update_property('x', x)

    def set_y(self, y):
        "Set y-axis position in mm"
        self._set_pos(y, self._y_mm_per_count, POS_ABS_Y)
        self._update_property('y', y)

    def set_z(self, z):
        "Set z-axis position in mm"
        self._set_pos(z, self._z_mm_per_count, POS_ABS_Z)
        self._update_property('z', z)

    def get_position(self):
        """Return (x,y,z) positionz in mm."""
        return self.get_x(), self.get_y(), self.get_z()

    def _get_pos(self, conversion_factor, command):
        counts = int(self.send_message(command, async=False, intent="get stage position").response)
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

    def reinit(self):
        self.reinit_x()
        self.reinit_y()
        self.reinit_z()

    def reinit_x(self):
        """Reinitialize x axis to correct for drift or "stuck" stage. Executes synchronously."""
        self.send_message(INIT_X, async=False, intent="init stage x axis")
        self._update_property('x', self.get_x())

    def reinit_y(self):
        """Reinitialize y axis to correct for drift or "stuck" stage. Executes synchronously."""
        self.send_message(INIT_Y, async=False, intent="init stage y axis")
        self._update_property('y', self.get_y())

    def reinit_z(self):
        """Reinitialize z axis to correct for drift or "stuck" stage. Executes synchronously."""
        self.send_message(INIT_RANGE_Z, async=False, intent="init stage z axis")
        self._update_property('z', self.get_z())

    def get_z_speed_range(self):
        """Return min, max z speed values in mm/second"""
        return self._z_speed_min, self._z_speed_max

    def get_z_speed(self):
        """Get z-axis speed in mm/second"""
        counts = int(self.send_message(GET_SPEED_Z, async=False, intent="get z speed").response)
        return counts * self._z_mm_per_count * Z_SPEED_MM_PER_SECOND_PER_UNIT

    def set_z_speed(self, speed):
        """Get z-axis speed in mm/second"""
        assert self._z_speed_min <= speed <= self._z_speed_max
        counts = int(round(speed / self._z_mm_per_count / Z_SPEED_MM_PER_SECOND_PER_UNIT))
        self.send_message(SET_SPEED_Z, counts, intent="set z speed")

    def get_z_ramp_range(self):
        """Return min, max z ramp values in mm/second^2"""
        return self._z_ramp_min, self._z_ramp_max

    def get_z_ramp(self):
        """Get z-axis ramp in mm/second^2"""
        counts = int(self.send_message(GET_RAMP_Z, async=False, intent="get z ramp").response)
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


    def calculate_movement_position(self, distance, t):
        """Calculate where the stage will be (relative to the starting position)
        for a move of a given distance (in mm) after t seconds have elapsed.
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
                return ( 0.5 * speed_ramp * ramp_time**2
                       + final_speed * (t-ramp_time)
                       + half_fudge)
            total_time = 2*ramp_time + non_ramp_time
            if t > total_time:
                t = total_time
            return ( 0.5 * speed_ramp * ramp_time**2
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
                with state_stack.pushed_state(self, z_speed=speed, z_ramp=ramp, async=False):
                    for d in test_distances:
                        time_move_to(z0 - d, d)
                        time_move_to(z0, d)
        times = numpy.array(times)
        distances = numpy.array(distances)
        speeds = numpy.array(speeds)
        ramps = numpy.array(ramps)
        _calibrate_speed_coefficients(times, distances, speeds, ramps)
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
    self._setup_device()
    return time_estimates

