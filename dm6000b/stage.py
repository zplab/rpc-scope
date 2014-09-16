import message_device

GET_CONVERSION_FACTOR_X = '72034'
GET_CONVERSION_FACTOR_Y = '73034'
GET_CONVERSION_FACTOR_Z = '71042'
POS_ABS_X = '72022'
POS_ABS_Y = '73022'
POS_ABS_Z = '71022'
GET_POS_X = '72023'
GET_POS_Y = '73023'
GET_POS_Z = '71023'

class Stage(message_device.LeicaAsyncDevice):
    def _setup_device(self):
        self._x_mm_per_count = float(self.send_message(GET_CONVERSION_FACTOR_X).response) * 1000
        self._y_mm_per_count = float(self.send_message(GET_CONVERSION_FACTOR_Y).response) * 1000
        self._z_mm_per_count = float(self.send_message(GET_CONVERSION_FACTOR_Z).response) * 1000
    
    def set_position(self, x=None, y=None, z=None):
        """Set position to x, y, and z. Any may be None to indicate no motion
        is requested. Units are in mm."""
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
    
    def set_y(self, y):
        "Set y-axis position in mm"
        self._set_pos(y, self._y_mm_per_count, POS_ABS_Y)
    
    def set_z(self, z):
        "Set z-axis position in mm"
        self._set_pos(z, self._z_mm_per_count, POS_ABS_Z)
    
    def _get_pos(self, conversion_factor, command):
        counts = int(self.send_message(command, async=False, intent="get stage position").response)
        mm = counts * conversion_factor
        return mm
    
    def get_x(self, x):
        """Get x-axis position in mm."""
        return _get_pos(self._x_mm_per_count, GET_POS_X)

    def get_y(self, y):
        """Get y-axis position in mm."""
        return _get_pos(self._y_mm_per_count, GET_POS_Y)

    def get_z(self, z):
        """Get z-axis position in mm."""
        return _get_pos(self._z_mm_per_count, GET_POS_Z)
        
        