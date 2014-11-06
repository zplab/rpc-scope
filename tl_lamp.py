class TL_Lamp:
    def __init__(self, iotool, property_server=None, property_prefix=''):
        self._iotool = iotool
        self._property_server = property_server
        self._property_prefix = property_prefix
        self.set(enable=False, intensity=255)
    
    def set(self, enable=None, intensity=None):
        """Set lamp on/off and brightness values
        enable: True (lamp on), False (lamp off), or None (no change).
        intensity: None (no change) or value in the range [0, 255] for min to max.
        """
        self._iotool.execute(self._iotool.commands.transmitted_lamp(enable, intensity))
        if self._property_server:
            if enable is not None:
                self._property_server.update_property(self._property_prefix+'enabled', enable)
            if intensity is not None:
                self._property_server.update_property(self._property_prefix+'intensity', intensity)
                