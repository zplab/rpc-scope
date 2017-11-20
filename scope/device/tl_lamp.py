# This code is licensed under the MIT License (see LICENSE file for details)

from ..util import property_device
from ..config import scope_configuration
from . import iotool

class SutterLED_Lamp(property_device.PropertyDevice):
    def __init__(self, iotool: iotool.IOTool, property_server=None, property_prefix=''):
        super().__init__(property_server, property_prefix)
        self._tlconfig = scope_configuration.get_config().sutter_led
        self._iotool = iotool
        self.set_enabled(False)
        self.set_intensity(self._tlconfig.INITIAL_INTENSITY)

    def _iotool_lamp_commands(self, enabled=None, intensity=None):
        """Produce a sequence of IOTool commands to enable/disable and control the
        intensity of the TL lamp.

        Parameters
            enabled: True (lamp on), False (lamp off), or None (no change).
            intensity: None (no change) or value in the range [0, 255].
        """
        commands = []
        if intensity is not None:
            assert 0 <= intensity <= self._tlconfig.IOTOOL_PWM_MAX
            commands.append(self._iotool.commands.pwm(self._tlconfig.IOTOOL_PWM_PIN, intensity))
        if enabled is not None:
            if enabled:
                commands.append(self._iotool.commands.set_high(self._tlconfig.IOTOOL_ENABLE_PIN))
            else:
                commands.append(self._iotool.commands.set_low(self._tlconfig.IOTOOL_ENABLE_PIN))
        return commands
    
    def set_enabled(self, enabled):
        """Turn lamp on or off.
        """
        self._enabled = enabled
        self._iotool.execute(*self._iotool_lamp_commands(enabled=enabled))
        self._update_property('enabled', enabled)

    def get_enabled(self):
        return self._enabled

    def _update_push_states(self, state, old_state):
        # superclass prevents pushing a state identical to the current one.
        # But for SutterLED_Lamp, this is useful in case something is going to use
        # IOTool to change the intensity behind the scenes and thus wants to
        # push the current intensity/enabled state onto the stack.
        pass

    def set_intensity(self, value):
        """Set intensity to any value in the range [0, 255] for min to max.
        """
        self._intensity = value
        self._iotool.execute(*self._iotool_lamp_commands(intensity=value))
        self._update_property('intensity', value)

    def get_intensity(self):
        return self._intensity



