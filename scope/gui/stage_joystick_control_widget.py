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

SDL_SUBSYSTEMS = sdl2.SDL_INIT_JOYSTICK | sdl2.SDL_INIT_GAMECONTROLLER
INPUT_STATE_CHANGED_EVENT = Qt.QEvent.registerEventType()
SDL_OPEN_INPUT_DEVICE_COMMAND_EVENT = sdl2.SDL_RegisterEvent(1)
SDL_CLOSE_INPUT_DEVICE_COMMAND_EVENT = sdl2.SDL_RegisterEvent(1)

class InputStateChanges:
    __slots__ = (
        'button_presses', # a temporally ordered list, if there were any button presses
        'axes_positions', # coalesced to current axis states, if any axis's position has changed
        'hats', # coalesced to current hat states, if any hat's position has changed
        'device_list', # latest device list, if it has changed
        'current_device_closed' # a True bool value, if the current device has been closed
    )
    def __bool__(self):
        return any(hasattr(self, slot) for slot in self.__slots__)

class SDLThread(threading.Thread):
    def __init__(self, widget):
        super().__init__(daemon=True, name='SDLThread')
        self.widget = widget
        self.quit_event_posted = False
        self.log_unhandled_SDL_events = True
        self.sdl_device = None
        self.input_state_changes = InputStateChanges()
        self.input_state_changes_lock = threading.Lock()

    def take_input_state_changes(self):
        'Intended to be called by StageJoystickControlWidget.'
        with self.input_state_changes_lock:
            input_state_changes = self.input_state_changes
            self.input_state_changes = InputStateChanges()
        return input_state_changes

    def run(self):
        assert sdl2.SDL_Init(SDL_SUBSYSTEMS) >= 0
        self.update_sdl_handlers()
        # The following SDL_SetHint call causes SDL2 to process joystick (and gamepad, as the
        # gamepad subsystem is built on the joystick subsystem) events without a window created
        # and owned by SDL2 focused or even extant.  In our case, we have no SDL2 window, and
        # we do not even initialize the SDL2 video subsystem.
        sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, b"1")
        if sdl2.SDL_JoystickEventState(sdl2.SDL_QUERY) != sdl2.SDL_ENABLE:
            sdl2.SDL_JoystickEventState(sdl2.SDL_ENABLE)
        if sdl2.SDL_GameControllerEventState(sdl2.SDL_QUERY) != sdl2.SDL_ENABLE:
            sdl2.SDL_GameControllerEventState(sdl2.SDL_ENABLE)
        sdl_event = sdl2.SDL_Event()
        while not self.quit_event_posted:
            if sdl2.SDL_WaitEvent(ctypes.byref(sdl_event)):
                self.sdl_event_handlers.get(sdl_event.type, self.on_unhandled_sdl_event)(sdl_event)
            else:
                sdl_e = sdl2.SDL_GetError()
                sdl_e = sdl_e.decode('ascii') if sdl_e else 'UNKNOWN ERROR'
                Qt.qDebug('SDL_WaitEvent error: {}'.format(sdl_e))
                sdl2.SDL_ClearError()
        sdl2.SDL_QuitSubSystem(SDL_SUBSYSTEMS)
        sdl2.SDL_Quit()
        Qt.qDebug('SDLThread is exiting gracefully.')

    def notify(self):
        # NB: In order to avoid occasionally deadlocking, it is essential that self.input_state_changes_lock
        # is not held by SDLThread when this method is called.
        self.widget.post_input_state_changed_event()

    def init_sdl_handlers(self):
        self.sdl_event_handlers = {
            sdl2.SDL_QUIT : self.on_quit
            sdl2.SDL_JOYDEVICEADDED : self.on_device_added,
            sdl2.SDL_JOYDEVICEREMOVED : self.on_device_removed,
            sdl2.SDL_CONTROLLERDEVICEADDED : self.on_device_added,
            sdl2.SDL_CONTROLLERDEVICEREMOVED : self.on_device_removed,
            SDL_OPEN_INPUT_DEVICE_COMMAND_EVENT : self.on_open_command,
            SDL_CLOSE_INPUT_DEVICE_COMMAND_EVENT : self.on_close_command
        }
        if self.sdl_device is None:
            return
        # TODO: add joystick & gamepad sdl event handlers for buttons and axes to self.sdl_event_handlers
        # depending on whether the device is a game controller or just a plain joystick
#       if sdl2.SDL_IsGameController():

    def on_unhandled_sdl_event(self, sdl_event):
        if self.log_unhandled_SDL_events:
            Qt.qDebug('Received unhandled SDL event: ' + SDL_EVENT_NAMES.get(sdl_event.type, "UNKNOWN"))

    def on_sdl_quit(self, sdl_event):
        self.quit_event_posted = True

class StageJoystickControlWidget(device_widget.DeviceWidget):
    def __init__(self, scope, scope_properties, parent=None):
        super().__init__(scope, scope_properties, parent)
        self.setWindowTitle('Stage Joystick Control')
        vlayout = Qt.QVBoxLayout()
        self.setLayout(vlayout)
        self.input_state_change_posted = False
        self.input_state_change_posted_lock = threading.Lock()
        self.sdl_thread = SDLThread(self)
        self.sdl_thread.start()

    def closeEvent(self, event):
        super().closeEvent(event)
        sdl_quit_event = sdl2.SDL_QuitEvent()
        sdl2.SDL_zero(sdl_quit_event)
        sdl_quit_event.type = sdl2.SDL_QUIT
        sdl2.SDL_PushEvent(ctypes.cast(ctypes.pointer(sdl_quit_event), ctypes.POINTER(sdl2.SDL_Event)))
        self.sdl_thread.join()

    def send_open_command(self, device_index):
        sdl_event = sdl2.SDL_Event()
        sdl2.SDL_zero(sdl_event)
        sdl_event.type = SDL_OPEN_INPUT_DEVICE_COMMAND_EVENT
        sdl_event.code = device_index
        sdl2.SDL_PushEvent(ctypes.byref(sdl_event))

    def send_close_command(self):
        sdl_event = sdl2.SDL_Event()
        sdl2.SDL_zero(sdl_event)
        sdl_event.type = SDL_CLOSE_INPUT_DEVICE_COMMAND_EVENT
        sdl2.SDL_PushEvent(ctypes.byref(sdl_event))

    def post_input_state_changed_event(self):
        'Intended to be called by SDLThread.'
        with self.input_state_change_posted_lock:
            if not self.input_state_change_posted:
                self.input_state_change_posted = True
                Qt.QCoreApplication.postEvent(self, Qt.QEvent(INPUT_STATE_CHANGED_EVENT))

    def event(self, event):
        if event.type() == INPUT_STATE_CHANGED_EVENT:
            with self.input_state_change_posted_lock:
                if not self.input_state_change_posted:
                    return True
                self.input_state_change_posted = False
            self.handle_input_state_changes(self.sdl_thread.take_input_state_changes())
            return True
        return super().event(event)

    def handle_input_state_changes(self, input_state_changes):
        print('handle_input_state_changes')

SDL_EVENT_NAMES = {
    sdl2.SDL_APP_DIDENTERBACKGROUND : 'SDL_APP_DIDENTERBACKGROUND',
    sdl2.SDL_APP_DIDENTERFOREGROUND : 'SDL_APP_DIDENTERFOREGROUND',
    sdl2.SDL_APP_LOWMEMORY : 'SDL_APP_LOWMEMORY',
    sdl2.SDL_APP_TERMINATING : 'SDL_APP_TERMINATING',
    sdl2.SDL_APP_WILLENTERBACKGROUND : 'SDL_APP_WILLENTERBACKGROUND',
    sdl2.SDL_APP_WILLENTERFOREGROUND : 'SDL_APP_WILLENTERFOREGROUND',
    sdl2.SDL_CLIPBOARDUPDATE : 'SDL_CLIPBOARDUPDATE',
    sdl2.SDL_CONTROLLERAXISMOTION : 'SDL_CONTROLLERAXISMOTION',
    sdl2.SDL_CONTROLLERBUTTONDOWN : 'SDL_CONTROLLERBUTTONDOWN',
    sdl2.SDL_CONTROLLERBUTTONUP : 'SDL_CONTROLLERBUTTONUP',
    sdl2.SDL_CONTROLLERDEVICEADDED : 'SDL_CONTROLLERDEVICEADDED',
    sdl2.SDL_CONTROLLERDEVICEREMAPPED : 'SDL_CONTROLLERDEVICEREMAPPED',
    sdl2.SDL_CONTROLLERDEVICEREMOVED : 'SDL_CONTROLLERDEVICEREMOVED',
    sdl2.SDL_DOLLARGESTURE : 'SDL_DOLLARGESTURE',
    sdl2.SDL_DOLLARRECORD : 'SDL_DOLLARRECORD',
    sdl2.SDL_DROPFILE : 'SDL_DROPFILE',
    sdl2.SDL_FINGERDOWN : 'SDL_FINGERDOWN',
    sdl2.SDL_FINGERMOTION : 'SDL_FINGERMOTION',
    sdl2.SDL_FINGERUP : 'SDL_FINGERUP',
    sdl2.SDL_FIRSTEVENT : 'SDL_FIRSTEVENT',
    sdl2.SDL_JOYAXISMOTION : 'SDL_JOYAXISMOTION',
    sdl2.SDL_JOYBALLMOTION : 'SDL_JOYBALLMOTION',
    sdl2.SDL_JOYBUTTONDOWN : 'SDL_JOYBUTTONDOWN',
    sdl2.SDL_JOYBUTTONUP : 'SDL_JOYBUTTONUP',
    sdl2.SDL_JOYDEVICEADDED : 'SDL_JOYDEVICEADDED',
    sdl2.SDL_JOYDEVICEREMOVED : 'SDL_JOYDEVICEREMOVED',
    sdl2.SDL_JOYHATMOTION : 'SDL_JOYHATMOTION',
    sdl2.SDL_KEYDOWN : 'SDL_KEYDOWN',
    sdl2.SDL_KEYUP : 'SDL_KEYUP',
    sdl2.SDL_LASTEVENT : 'SDL_LASTEVENT',
    sdl2.SDL_MOUSEBUTTONDOWN : 'SDL_MOUSEBUTTONDOWN',
    sdl2.SDL_MOUSEBUTTONUP : 'SDL_MOUSEBUTTONUP',
    sdl2.SDL_MOUSEMOTION : 'SDL_MOUSEMOTION',
    sdl2.SDL_MOUSEWHEEL : 'SDL_MOUSEWHEEL',
    sdl2.SDL_MULTIGESTURE : 'SDL_MULTIGESTURE',
    sdl2.SDL_QUIT : 'SDL_QUIT',
    sdl2.SDL_RENDER_DEVICE_RESET : 'SDL_RENDER_DEVICE_RESET',
    sdl2.SDL_RENDER_TARGETS_RESET : 'SDL_RENDER_TARGETS_RESET',
    sdl2.SDL_SYSWMEVENT : 'SDL_SYSWMEVENT',
    sdl2.SDL_TEXTEDITING : 'SDL_TEXTEDITING',
    sdl2.SDL_TEXTINPUT : 'SDL_TEXTINPUT',
    sdl2.SDL_WINDOWEVENT : 'SDL_WINDOWEVENT'
}
