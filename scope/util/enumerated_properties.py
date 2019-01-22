# This code is licensed under the MIT License (see LICENSE file for details)

# Base classes capable of being made available through RPC for properties limited to
# predetermined or run-time determined sets of valid values.


class DictProperty:
    """Base class for any enumerated device property that is limited to a set of non-user-
    friendly values identified to the user by more meaningful names.
    """

    def __init__(self):
        self._hw_to_usr = self._get_hw_to_usr()
        self._usr_to_hw = {usr: hw for hw, usr in self._hw_to_usr.items()}

    def get_recognized_values(self):
        """The list of recognized values for this property."""
        return list(sorted(self._usr_to_hw.keys()))

    def get_value(self):
        """The current value."""
        return self._hw_to_usr[self._read()]

    def _get_hw_to_usr(self):
        raise NotImplementedError()

    def _read(self):
        raise AttributeError("can't get attribute")

    def set_value(self, value):
        if value not in self._usr_to_hw:
            raise ValueError('value must be one of {}.'.format(sorted(self.get_recognized_values())))
        self._write(self._usr_to_hw[value])

    def _write(self, value):
        raise AttributeError("can't set attribute")
