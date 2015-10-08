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

import contextlib
import ctypes
import sdl2
import sys
from scope.simple_rpc import rpc_client
from scope import scope_client

SDL_SUBSYSTEMS = sdl2.SDL_INIT_JOYSTICK | sdl2.SDL_INIT_GAMECONTROLLER | sdl2.SDL_INIT_TIMER
SDL_INITED = False
SDL_EVENT_LOOP_IS_RUNNING = False

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

def init_sdl():
    global SDL_INITED
    if SDL_INITED:
        # Prompt SDL to process any input queued by the OS, generating SDL events
        sdl2.SDL_PumpEvents()
        # Get rid of those and any other accumulated SDL events
        sdl2.SDL_FlushEvents(sdl2.SDL_FIRSTEVENT, 2**32 - 1)
    else:
        if sdl2.SDL_Init(SDL_SUBSYSTEMS) < 0:
            sdl_e = sdl2.SDL_GetError()
            sdl_e = sdl_e.decode('utf-8') if sdl_e else 'UNKNOWN ERROR'
            sdl2.SDL_Quit()
            raise RuntimeError('Failed to initialize SDL ("{}").'.format(sdl_e))
        # The following SDL_SetHint call causes SDL2 to process joystick (and gamepad, as the
        # gamepad subsystem is built on the joystick subsystem) events without a window created
        # and owned by SDL2 focused or even extant.  In our case, we have no SDL2 window, and
        # we do not even initialize the SDL2 video subsystem.
        sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, b"1")
        if sdl2.SDL_JoystickEventState(sdl2.SDL_QUERY) != sdl2.SDL_ENABLE:
            sdl2.SDL_JoystickEventState(sdl2.SDL_ENABLE)
        if sdl2.SDL_GameControllerEventState(sdl2.SDL_QUERY) != sdl2.SDL_ENABLE:
            sdl2.SDL_GameControllerEventState(sdl2.SDL_ENABLE)
        SDL_INITED = True
        def deinit_sdl():
            sdl2.SDL_QuitSubSystem(SDL_SUBSYSTEMS)
            sdl2.SDL_Quit()
        import atexit
        atexit.register(deinit_sdl)

def enumerate_devices():
    with contextlib.ExitStack() as estack:
        # We may be called from a different thread than the one that will run the SDL event loop.  In case that
        # will happen, if SDL is not already initialized, we do not leave it initialized - bound to our current
        # thread.
        if not SDL_INITED:
            if sdl2.SDL_Init(sdl2.SDL_INIT_JOYSTICK) < 0:
                sdl_e = sdl2.SDL_GetError()
                sdl_e = sdl_e.decode('utf-8') if sdl_e else 'UNKNOWN ERROR'
                sdl2.SDL_Quit()
                raise RuntimeError('Failed to initialize SDL ("{}").'.format(sdl_e))
            estack.callback(lambda: sdl2.SDL_QuitSubSystem(sdl2.SDL_INIT_JOYSTICK))
            estack.callback(sdl2.SDL_Quit)
        names = [sdl2.SDL_JoystickNameForIndex(sdl_dev_idx).decode('utf-8') for sdl_dev_idx in range(sdl2.SDL_NumJoysticks())]
    return names

def only_for_our_device(handler):
    def f(self, event):
        try:
            event_device_id = event.jdevice.which
        except:
            return
        if event_device_id == self.device_id:
            return handler(self, event)
    return f

class SDLControl:
    def __init__(
            self,
            input_device_index=0,
            input_device_name=None,
            scope_server_host='127.0.0.1',
            zmq_context=None,
            maximum_portion_of_wallclock_time_allowed_for_axis_commands=0.5):
        '''* input_device_index: The argument passed to SDL_JoystickOpen(index) or SDL_GameControllerOpen(index).
        Ignored if the value of input_device_name is not None.
        * input_device_name: If specified, input_device_name should be the exact string or UTF8-encoded bytearray
        by which SDL identifies the controller you wish to use, as reported by SDL_JoystickName(..).  For USB devices,
        this is USB iManufacturer + ' ' + iProduct.  EG, a Sony PS4 controller with the following lsusb -v output would
        be known to SDL as 'Sony Computer Entertainment Wireless Controller':

        Bus 003 Device 041: ID 054c:05c4 Sony Corp.
        Device Descriptor:
          bLength                18
          bDescriptorType         1
          bcdUSB               2.00
          bDeviceClass            0
          bDeviceSubClass         0
          bDeviceProtocol         0
          bMaxPacketSize0        64
          idVendor           0x054c Sony Corp.
          idProduct          0x05c4
          bcdDevice            1.00
          iManufacturer           1 Sony Computer Entertainment
          iProduct                2 Wireless Controller
          iSerial                 0
          bNumConfigurations      1
        ...

        Additionally, sdl_control.enumerate_devices(), a module function, returns a list of the currently available
        SDL joystick and gamepad input devices, in the order by which SDL knows them.  So, if you know that
        your input device is a Logilech something-or-other, and sdl_control.enumerate_devices() returns the following:
        [
            'Nintenbo Olympic Sport Mat v3.5',
            'MANUFACTURER NAME HERE. DONT FORGET TO SET THIS!!     Many Product Ltd. 1132 Guangzhou    $  !*llSN9_Q   ',
            'Duckhunt Defender Scanline-Detecting Plastic Gun That Sadly Does Not Work With LCDs',
            'Macrosoft ZBox-720 Controller Colossal-Hands Mondo Edition',
            'Logilech SixThousandAxis KiloButtonPad With Haptic Feedback Explosion',
            'Gametech Gameseries MegaGamer Excel Spreadsheet 3D-Orb For Executives, Doom3D Edition',
            'Gametech Gameseries MegaGamer Excel Spreadsheet 3D-Orb For Light Rail Transport, Doom3D Edition'
        ]
        You will therefore want to specify input_device_index=4 or
        input_device_name='Logilech SixThousandAxis KiloButtonPad With Haptic Feedback Explosion'.'''
        if input_device_name is None and int(input_device_index) != input_device_index:
            raise ValueError('If input_device_name is not specified, the value supplied for input_device_index must be an integer.')
        init_sdl()
        input_device_count = sdl2.SDL_NumJoysticks()
        if input_device_count == 0:
            raise RuntimeError('According to SDL, there are no joysticks/gamepads attached.')
        if input_device_name is None:
            if not 0 <= input_device_index < input_device_count:
                isare, ssuffix = ('is', '') if input_device_count == 1 else ('are', 's')
                e = ('According to SDL, there {0} {1} joystick{2}/gamepad{2} attached.  Therefore, input_device_index must be '
                     'an integer in the closed interval [0, {3}], which the supplied value, {4}, is not.')
                raise ValueError(e.format(isare, input_device_count, ssuffix, input_device_count - 1, input_device_index))
            input_device_name = sdl2.SDL_JoystickNameForIndex(input_device_index)
        else:
            if isinstance(input_device_name, str):
                input_device_name = input_device_name.encode('utf-8')
            else:
                input_device_name = bytes(input_device_name)
            for sdl_dev_idx in range(sdl2.SDL_NumJoysticks()):
                if sdl2.SDL_JoystickNameForIndex(sdl_dev_idx) == input_device_name:
                    input_device_index = sdl_dev_idx
                    break
            else:
                raise ValueError('No connected joystick or gamepad device recognized by SDL has the name "{}".'.format(input_device_name.decode('utf-8')))
        self.device_is_game_controller = bool(sdl2.SDL_IsGameController(input_device_index))
        self.device = (sdl2.SDL_GameControllerOpen if self.device_is_game_controller else sdl2.SDL_JoystickOpen)(input_device_index)
        if not self.device:
            raise RuntimeError('Failed to open {} at device index {} with name "{}".'.format(
                'game controller' if self.device_is_game_controller else 'joystick',
                input_device_index,
                input_device_name.decode('utf-8')))
        if self.device_is_game_controller:
            self.device_id = sdl2.SDL_JoystickInstanceID(sdl2.SDL_GameControllerGetJoystick(self.device))
        else:
            self.device_id = sdl2.SDL_JoystickInstanceID(self.device)
        print('SDLControl is connecting to scope server...', file=sys.stderr)
        self.scope, self.scope_properties = scope_client.client_main(scope_server_host, zmq_context)
        print('SDLControl successfully connected to scope server.', file=sys.stderr)
        self.event_loop_is_running = False
        self.warn_on_unhandled_events = False
        self.quit_event_posted = False

    def _init_handlers(self):
        self._event_handlers = {
            sdl2.SDL_QUIT : self._on_quit
        }
        if self.device_is_game_controller:
            self._event_handlers.update({
                sdl2.SDL_CONTROLLERDEVICEREMOVED : self._on_device_removed,
                sdl2.SDL_CONTROLLERAXISMOTION : self._on_axis_motion
            })
        else:
            self._event_handlers.update({
                sdl2.SDL_JOYDEVICEREMOVED : self._on_device_removed,
                sdl2.SDL_JOYAXISMOTION : self._on_axis_motion
            })

    def event_loop(self):
        global SDL_EVENT_LOOP_IS_RUNNING
        assert not SDL_EVENT_LOOP_IS_RUNNING
        SDL_EVENT_LOOP_IS_RUNNING = True
        def on_loop_end():
            global SDL_EVENT_LOOP_IS_RUNNING
            SDL_EVENT_LOOP_IS_RUNNING = False
        with contextlib.ExitStack() as estack:
            estack.callback(on_loop_end)
            assert SDL_INITED
            assert self.device
            self._init_handlers()
            try:
                while not self.quit_event_posted:
                    event = sdl2.SDL_Event()
                    # If there is no event for an entire second, we iterate, giving CPython an opportunity to
                    # raise KeyboardInterrupt.
                    if sdl2.SDL_WaitEventTimeout(ctypes.byref(event), 1000):
                        self._event_handlers.get(event.type, self._on_unhandled_event)(event)
            except KeyboardInterrupt:
                pass

    def exit_event_loop(self):
        '''The exit_event_loop method is thread safe and is safe to call even if the event loop is not running.
        Calling exit_event_loop pushes a quit request onto the SDL event queue, causing self.event_loop() to
        exit gracefully (IE, return) if it is running.'''
        event = sdl2.SDL_Event()
        event.type = sdl2.SDL_QUIT
        sdl2.SDL_PushEvent(ctypes.byref(event))

    def _on_quit(self, event):
        self.quit_event_posted = True

    def _on_unhandled_event(self, event):
        if self.warn_on_unhandled_events:
            print('Received unhandled SDL event: ' + SDL_EVENT_NAMES.get(event.type, "UNKNOWN"), file=sys.stderr)

    @only_for_our_device
    def _on_device_removed(self, event):
        print('Our SDL input device has been disconnected.  Exiting event loop...', sys.stderr)
        self.exit_event_loop()

    @only_for_our_device
    def _on_axis_motion(self, event):
        print('axis {} value {}'.format(event.jaxis.axis, event.jaxis.value))
        i = event.jaxis.value
        demand = i / (32768 if i <= 0 else 32767)
        velocity = demand * 2
        if event.jaxis.axis == 0:
            self.scope.stage.move_along_x(-velocity)
        elif event.jaxis.axis == 1:
            self.scope.stage.move_along_y(velocity)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(epilog='Note: Either device name/index or --list must be supplied as arguments, but not both.')
    parser.add_argument('--scope', default='127.0.0.1', help='Hostname or IP address of the scope server.  Defaults to "127.0.0.1".')
    parserg = parser.add_mutually_exclusive_group(required=True)
    parserg.add_argument(
        '--list',
        action='store_true',
        help="Print a list of the acceptable SDL devices' indexes and names, with one device per line."
    )
    parserg.add_argument('device', nargs='?', help='SDL input device name or index.')
    args = parser.parse_args()
    if args.list:
        for idx, name in enumerate(enumerate_devices()):
            print('{}: "{}"'.format(idx, name))
    else:
        if args.device.isdigit():
            sdlc = SDLControl(input_device_index=int(args.device), scope_server_host=args.scope)
        else:
            sdlc = SDLControl(input_device_name=args.device, scope_server_host=args.scope)
        sdlc.event_loop()

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
