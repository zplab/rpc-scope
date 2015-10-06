# The MIT License (MIT)
#
# Copyright (c) 2015 WUSTL ZPLAB
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

import ctypes
from PyQt5 import Qt
import sdl2
import threading
from . import device_widget
from ..simple_rpc import rpc_client

FRESH_JOYSTICK_INPUT_EVENT = Qt.QEvent.registerEventType()

class SDLThread(threading.Thread):
    def __init__(self, widget):
        super().__init__()
        self.want_exit = False
        self.widget = widget

    def run(self):
        assert sdl2.SDL_Init(sdl2.SDL_INIT_JOYSTICK) >= 0
        sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, b"1")
        joystick = sdl2.SDL_JoystickOpen(0)
        while not self.want_exit:
            sdl_event = sdl2.SDL_Event()
            sdl2.SDL_JoystickUpdate()
            while sdl2.SDL_WaitEventTimeout(ctypes.byref(sdl_event), 500):
                self.widget.post_fresh_joystick_input_event(sdl_event)
        sdl2.SDL_JoystickClose(joystick)
        sdl2.SDL_QuitSubSystem(sdl2.SDL_INIT_JOYSTICK)
        sdl2.SDL_Quit()

class StageJoystickControlWidget(device_widget.DeviceWidget):
    def __init__(self, scope, scope_properties, parent=None):
        super().__init__(scope, scope_properties, parent)
        self.setWindowTitle('Stage Joystick Control')
        vlayout = Qt.QVBoxLayout()
        self.setLayout(vlayout)
        self.sdl_thread = SDLThread(self)
        self.sdl_thread.start()
        self.fresh_joystick_input_event_lock = threading.Lock()
        self.fresh_joystick_input_event = None
        self.i = 0

    def closeEvent(self, event):
        self.sdl_thread.want_exit = True
        self.sdl_thread.join()
        event.accept()

    def post_fresh_joystick_input_event(self, sdl_event):
        with self.fresh_joystick_input_event_lock:
            event_is_first_in_this_iteration = self.fresh_joystick_input_event is None
            self.fresh_joystick_input_event = sdl_event
            if event_is_first_in_this_iteration:
                Qt.QCoreApplication.postEvent(self, Qt.QEvent(FRESH_JOYSTICK_INPUT_EVENT))

    def event(self, event):
        if event.type() == FRESH_JOYSTICK_INPUT_EVENT:
            import time
            print('FRESH_JOYSTICK_INPUT_EVENT!', self.i)
            self.i += 1
            with self.fresh_joystick_input_event_lock:
                self.fresh_joystick_input_event = None
            return True
        return super().event(event)

if __name__ == '__main__':
    import sys
    from rpc_acquisition.scope import scope_client
    scope, scope_properties = scope_client.client_main('scope')
    app = Qt.QApplication(sys.argv)
    sjcw = StageJoystickControlWidget(scope, scope_properties)
    sjcw.show()
    app.exec_()
