from .simple_rpc import property_utils

class TL_Lamp(property_utils.PropertyDevice):
    def __init__(self, iotool, property_server=None, property_prefix=''):
        super().__init__(property_server, property_prefix)
        self._iotool = iotool
        self.set_enabled(False)
        self.set_intensity(255)

    def set_enabled(self, enable):
        """Turn lamp on or off.
        """
        self._iotool.execute(*self._iotool.commands.transmitted_lamp(enable=enable))
        self._update_property('enabled', enable)


    def set_intensity(self, value):
        """Set intensity to any value in the range [0, 255] for min to max.
        """
        self._iotool.execute(*self._iotool.commands.transmitted_lamp(intensity=value))
        self._update_property('intensity', value)
