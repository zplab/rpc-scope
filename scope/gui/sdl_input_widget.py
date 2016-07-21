# The MIT License (MIT)
#
# Copyright (c) 2016 WUSTL ZPLAB
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
# Authors: Erik Hvatum <ice.rikh@gmail.com>

from PyQt5 import Qt
from ..client_util import sdl_input

class _SDLInputEventLoopThread(Qt.QThread):
    def __init__(self, sdl_input, parent=None):
        super().__init__(parent)
        self.sdl_input = sdl_input

    def run(self):
        self.sdl_input.event_loop()

class _SDLInput(sdl_input.SDLInput):
    def __init__(
            self,
            sdl_input_widget,
            input_device_index=0,
            input_device_name=None,
            scope_server_host='127.0.0.1',
            zmq_context=None,
            maximum_portion_of_wallclock_time_allowed_for_axis_commands=sdl_input.SDLInput.DEFAULT_MAX_AXIS_COMMAND_WALLCLOCK_TIME_PORTION,
            maximum_axis_command_cool_off=sdl_input.SDLInput.DEFAULT_MAX_AXIS_COMMAND_COOL_OFF):
        super().__init__(
            input_device_index=input_device_index,
            input_device_name=input_device_name,
            scope_server_host=scope_server_host,
            zmq_context=zmq_context,
            maximum_portion_of_wallclock_time_allowed_for_axis_commands=maximum_portion_of_wallclock_time_allowed_for_axis_commands,
            maximum_axis_command_cool_off=maximum_axis_command_cool_off)
        self.sdl_input_widget = sdl_input_widget

    def handle_button(self, button_idx, pressed):
        self.sdl_input_widget.button_signal.emit(button_idx, pressed)

    def handle_joyhatmotion(self, hat_idx, pos):
        self.sdl_input_widget.hat_signal.emit(hat_idx, pos)

class SDLInputWidget(Qt.QWidget):
    button_signal = Qt.pyqtSignal(int, bool)
    hat_signal = Qt.pyqtSignal(int, int)

    @staticmethod
    def can_run(scope):
        return True

    def __init__(self, host, scope, scope_properties, parent=None):
        super().__init__(parent)
        self.sdl_input = _SDLInput(self, scope_server_host=host)
        self.setWindowTitle('SDL Input')
        self.sdl_input_event_loop_thread = _SDLInputEventLoopThread(self.sdl_input)
        self.sdl_input_event_loop_thread.start()
        Qt.QApplication.instance().aboutToQuit.connect(self.sdl_input.exit_event_loop)

    # TODO: add button for connecting/disconnecting.  show error when "connect" is clicked and no sdl inputs are
    # available.  connect to the only available sdl input if there is only one.  display a dialog with a list
    # of available sdl inputs if more than one are available, with ok and cancel prompt.