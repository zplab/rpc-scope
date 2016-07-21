# The MIT License (MIT)
#
# Copyright (c) 2015-2016 WUSTL ZPLAB
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
import threading
from scope import scope_client

SDL_SUBSYSTEMS = sdl2.SDL_INIT_JOYSTICK | sdl2.SDL_INIT_GAMECONTROLLER | sdl2.SDL_INIT_TIMER
SDL_INITED = False
SDL_TIMER_CALLBACK_TYPE = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p)

def init_sdl():
    global SDL_INITED
    if SDL_INITED:
        sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, b"1")
    else:
        if sdl2.SDL_Init(SDL_SUBSYSTEMS) < 0:
            sdl_e = sdl2.SDL_GetError()
            sdl_e = sdl_e.decode('utf-8') if sdl_e else 'UNKNOWN ERROR'
            sdl2.SDL_Quit()
            raise RuntimeError('Failed to initialize SDL ("{}").'.format(sdl_e))
        # The following SDL_SetHint call causes SDL2 to process joystick (and game controller, as the
        # game controller subsystem is built on the joystick subsystem) events without a window created
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
        # will happen, if SDL is not already initialized, we do not leave it initialized (if we did, it would be
        # bound to our current thread, which may not be desired).
        if not SDL_INITED:
            if sdl2.SDL_Init(sdl2.SDL_INIT_JOYSTICK | sdl2.SDL_INIT_GAMECONTROLLER) < 0:
                sdl_e = sdl2.SDL_GetError()
                sdl_e = sdl_e.decode('utf-8') if sdl_e else 'UNKNOWN ERROR'
                sdl2.SDL_Quit()
                raise RuntimeError('Failed to initialize SDL ("{}").'.format(sdl_e))
            estack.callback(lambda: sdl2.SDL_QuitSubSystem(sdl2.SDL_INIT_JOYSTICK | sdl2.SDL_INIT_GAMECONTROLLER))
            estack.callback(sdl2.SDL_Quit)
        rows = []
        for sdl_dev_idx in range(sdl2.SDL_NumJoysticks()):
            device_is_game_controller = bool(sdl2.SDL_IsGameController(sdl_dev_idx))
            device_type = 'game controller' if device_is_game_controller else 'joystick'
            cols = [sdl_dev_idx, device_type, sdl2.SDL_JoystickNameForIndex(sdl_dev_idx).decode('utf-8')]
            if device_is_game_controller:
                cols.append(sdl2.SDL_GameControllerNameForIndex(sdl_dev_idx).decode('utf-8'))
            rows.append(cols)
    return rows

def open_device(input_device_index=0, input_device_name=None, _used_idx_and_name=None):
    if input_device_name is None and int(input_device_index) != input_device_index:
        raise ValueError('If input_device_name is not specified, the value supplied for input_device_index must be an integer.')
    input_device_count = sdl2.SDL_NumJoysticks()
    if input_device_count == 0:
        raise RuntimeError('According to SDL, there are no joysticks/game controllers attached.')
    if input_device_name is None:
        if not 0 <= input_device_index < input_device_count:
            isare, ssuffix = ('is', '') if input_device_count == 1 else ('are', 's')
            e = ('According to SDL, there {0} {1} joystick{2}/game controller{2} attached.  Therefore, input_device_index must be '
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
            raise ValueError('No connected joystick or game controller device recognized by SDL has the name "{}".'.format(input_device_name.decode('utf-8')))
    device_is_game_controller = bool(sdl2.SDL_IsGameController(input_device_index))
    device = (sdl2.SDL_GameControllerOpen if device_is_game_controller else sdl2.SDL_JoystickOpen)(input_device_index)
    if not device:
        raise RuntimeError('Failed to open {} at device index {} with name "{}".'.format(
            'game controller' if device_is_game_controller else 'joystick',
            input_device_index,
            input_device_name.decode('utf-8'))
        )
    if _used_idx_and_name is not None:
        _used_idx_and_name[0] = input_device_index
        _used_idx_and_name[1] = input_device_name
    return device, device_is_game_controller

def dump_input(input_device_index=0, input_device_name=None):
    init_sdl()
    used_idx_and_name = [None, None]
    device, device_is_game_controller = open_device(input_device_index, input_device_name, used_idx_and_name)
    device_id = sdl2.SDL_JoystickInstanceID(sdl2.SDL_GameControllerGetJoystick(device) if device_is_game_controller else device)
    if device_is_game_controller:
        s = 'Opened game controller, c_name "{}", j_name "{}", idx {}, j_id {}'.format(
            sdl2.SDL_GameControllerName(device).decode('utf-8'),
            used_idx_and_name[1].decode('utf-8'),
            used_idx_and_name[0],
            device_id
        )
    else:
        s = 'Opened joystick, j_name "{}", idx {}, j_id {}'.format(
            used_idx_and_name[1].decode('utf-8'),
            used_idx_and_name[0],
            device_id
        )
    print(s)
    def on_joydeviceaddedevent(event):
        return 'idx: {} j_name: {}'.format(event.jdevice.which, sdl2.SDL_JoystickNameForIndex(event.jdevice.which).decode('utf-8'))
    def on_joydeviceremovedevent(event):
        return 'j_id: {}'.format(event.jdevice.which)
    def on_joyaxismotionevent(event):
        return 'j_id: {} axis: {} pos: {}'.format(event.jaxis.which, event.jaxis.axis, event.jaxis.value)
    def on_joyballmotionevent(event):
        return 'j_id: {} ball: {} xdelta: {} ydelta: {}'.format(event.jball.which, event.jball.ball, event.jball.xrel, event.jball.yrel)
    def on_joyhatmotionevent(event):
        return 'j_id: {} hat: {} pos: {}'.format(event.jhat.which, event.jhat.hat, SDL_HAT_DIRECTION_NAMES.get(event.jhat.value, event.jhat.value))
    def on_joybuttonevent(event):
        return 'j_id: {} button: {} state: {}'.format(
            event.jbutton.which,
            event.jbutton.button,
            'is_pressed' if bool(event.jbutton.state) else 'is_not_pressed'
        )
    def on_controllerdeviceaddedevent(event):
        return 'idx: {} c_name: {}'.format(event.cdevice.which, sdl2.SDL_GameControllerNameForIndex(event.cdevice.which).decode('utf-8'))
    def on_controllerdeviceremovedevent(event):
        return 'c_id: {}'.format(event.cdevice.which)
    def on_controlleraxismotionevent(event):
        return 'c_id: {} axis: {} pos: {}'.format(
            event.caxis.which,
            SDL_CONTROLLER_AXIS_NAMES.get(event.caxis.axis, event.caxis.axis),
            event.caxis.value
        )
    def on_controllerbuttonevent(event):
        return 'c_id: {} button: {} state: {}'.format(
            event.cbutton.which,
            SDL_CONTROLLER_BUTTON_NAMES.get(event.cbutton.button, event.cbutton.button),
            'is_pressed' if bool(event.cbutton.state) else 'is_not_pressed'
        )
    event_handlers = {
        sdl2.SDL_JOYDEVICEADDED: on_joydeviceaddedevent,
        sdl2.SDL_JOYDEVICEREMOVED: on_joydeviceremovedevent,
        sdl2.SDL_JOYAXISMOTION: on_joyaxismotionevent,
        sdl2.SDL_JOYBALLMOTION: on_joyballmotionevent,
        sdl2.SDL_JOYHATMOTION: on_joyhatmotionevent,
        sdl2.SDL_JOYBUTTONDOWN: on_joybuttonevent,
        sdl2.SDL_JOYBUTTONUP: on_joybuttonevent,
        sdl2.SDL_CONTROLLERDEVICEADDED: on_controllerdeviceaddedevent,
        sdl2.SDL_CONTROLLERDEVICEREMOVED: on_controllerdeviceremovedevent,
        sdl2.SDL_CONTROLLERAXISMOTION: on_controlleraxismotionevent,
        sdl2.SDL_CONTROLLERBUTTONDOWN: on_controllerbuttonevent,
        sdl2.SDL_CONTROLLERBUTTONUP: on_controllerbuttonevent
    }
    print('# milliseconds since SDL initialization, SDL_EventType, some event-type-specific information (not necessarily exhaustive)')
    try:
        while 1:
            event = sdl2.SDL_Event()
            # If there is no event for an entire second, we iterate, giving CPython an opportunity to
            # raise KeyboardInterrupt.
            if sdl2.SDL_WaitEventTimeout(ctypes.byref(event), 1000):
                if hasattr(event, 'generic'):
                    s = '{}, {}'.format(event.generic.timestamp, SDL_EVENT_NAMES.get(event.type, "UNKNOWN"))
                else:
                    s = '{}, {}'.format(event.common.timestamp, SDL_EVENT_NAMES.get(event.type, "UNKNOWN"))
                try:
                    s += ', {}'.format(event_handlers[event.type](event))
                except KeyError:
                    pass
                print(s)
                if event.type == sdl2.SDL_QUIT:
                    print('# SDL_QUIT received.  Exiting dump_input(..) ...')
                    break
                if event.type == sdl2.SDL_JOYDEVICEREMOVED and event.jdevice.which == device_id:
                    print('# Our SDL input device has been disconnected.  Exiting dump_input(..) ...')
                    break
    except KeyboardInterrupt:
        print('\n# ctrl-c received.  Exiting dump_input(..) ...')

def only_for_our_device(handler):
    def f(self, event):
        try:
            event_device_id = event.jdevice.which
        except:
            return
        if event_device_id == self.device_id:
            return handler(self, event)
    return f

class SDLInput:
    DEFAULT_MAX_AXIS_COMMAND_WALLCLOCK_TIME_PORTION = 0.3333
    DEFAULT_MAX_AXIS_COMMAND_COOL_OFF = 500
    # AXES_THROTTLE_DELAY_EXPIRED_EVENT: Sent by the timer thread to wake up the main
    # SDL thread and cause it to update the scope state in response to any axis position changes
    # that have occurred since last updating the scope for an axis position change.
    AXES_THROTTLE_DELAY_EXPIRED_EVENT = sdl2.SDL_RegisterEvents(1)
    COARSE_DEMAND_FACTOR = 20
    FINE_DEMAND_FACTOR = 1
    Z_DEMAND_FACTOR = 0.5
    AXIS_MOVEMENT_HANDLERS = {
        sdl2.SDL_CONTROLLER_AXIS_LEFTX: lambda self, demand: self.scope.stage.move_along_x(-demand * self.COARSE_DEMAND_FACTOR),
        sdl2.SDL_CONTROLLER_AXIS_LEFTY: lambda self, demand: self.scope.stage.move_along_y(demand * self.COARSE_DEMAND_FACTOR),
        sdl2.SDL_CONTROLLER_AXIS_RIGHTX: lambda self, demand: self.scope.stage.move_along_x(-demand * self.FINE_DEMAND_FACTOR),
        sdl2.SDL_CONTROLLER_AXIS_RIGHTY: lambda self, demand: self.scope.stage.move_along_y(demand * self.FINE_DEMAND_FACTOR),
        sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT: lambda self, demand: self.scope.stage.move_along_z(-demand * self.Z_DEMAND_FACTOR),
        sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT: lambda self, demand: self.scope.stage.move_along_z(demand * self.Z_DEMAND_FACTOR)
    }
    AXIS_DEAD_ZONES = {
        sdl2.SDL_CONTROLLER_AXIS_LEFTX: (-2000, 2000),
        sdl2.SDL_CONTROLLER_AXIS_LEFTY: (-2000, 2000),
        sdl2.SDL_CONTROLLER_AXIS_RIGHTX: (-2000, 2000),
        sdl2.SDL_CONTROLLER_AXIS_RIGHTY: (-2000, 2000)
    }

    def __init__(
            self,
            input_device_index=0,
            input_device_name=None,
            scope_server_host='127.0.0.1',
            zmq_context=None,
            maximum_portion_of_wallclock_time_allowed_for_axis_commands=DEFAULT_MAX_AXIS_COMMAND_WALLCLOCK_TIME_PORTION,
            maximum_axis_command_cool_off=DEFAULT_MAX_AXIS_COMMAND_COOL_OFF):
        """* input_device_index: The argument passed to SDL_JoystickOpen(index) or SDL_GameControllerOpen(index).
        Ignored if the value of input_device_name is not None.
        * input_device_name: If specified, input_device_name should be the exact string or UTF8-encoded bytearray by
        which SDL identifies the controller you wish to use, as reported by SDL_JoystickName(..).  For USB devices,
        this is USB iManufacturer + ' ' + iProduct.  (See example below.)
        * scope_server_host: IP address or hostname of scope server.
        * zmq_context: If None, one is created.
        * maximum_portion_of_wallclock_time_allowed_for_axis_commands: Limit the rate at which commands are sent to
        the scope in response to controller axis motion such that the scope such that the scope is busy processing
        those commands no more
        than this fraction of the time.
        * maximum_axis_command_cool_off: The maximum number of milliseconds to defer issuance of scope commands in
        response to controller axis motion (in order to enforce
        maximum_portion_of_wallclock_time_allowed_for_axis_commands).

        For example, a Sony PS4 controller with the following lsusb -v output would be known to SDL as 'Sony Computer
        Entertainment Wireless Controller':

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
        SDL joystick and game controller input devices, in the order by which SDL knows them.  So, if you know that
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
        input_device_name='Logilech SixThousandAxis KiloButtonPad With Haptic Feedback Explosion'
        """
        assert 0 < maximum_portion_of_wallclock_time_allowed_for_axis_commands <= 1
        init_sdl()
        self.device, self.device_is_game_controller = open_device(input_device_index, input_device_name)
        if self.device_is_game_controller:
            self.jdevice = sdl2.SDL_GameControllerGetJoystick(self.device)
        else:
            self.jdevice = self.device
        self.device_id = sdl2.SDL_JoystickInstanceID(self.jdevice)
        self.num_axes = sdl2.SDL_JoystickNumAxes(self.jdevice)
        self.num_buttons = sdl2.SDL_JoystickNumButtons(self.jdevice)
        self.num_hats = sdl2.SDL_JoystickNumHats(self.jdevice)
        print('SDLInput is connecting to scope server...', file=sys.stderr)
        self.scope, self.scope_properties = scope_client.client_main(scope_server_host, zmq_context)
        print('SDLInput successfully connected to scope server.', file=sys.stderr)
        self.event_loop_is_running = False
        self.warnings_enabled = False
        self.quit_event_posted = False
        self.throttle_delay_command_time_ratio = 1 - maximum_portion_of_wallclock_time_allowed_for_axis_commands
        self.throttle_delay_command_time_ratio /= maximum_portion_of_wallclock_time_allowed_for_axis_commands
        self.maximum_axis_command_cool_off = maximum_axis_command_cool_off
        self._axes_throttle_delay_lock = threading.Lock()
        self._c_on_axes_throttle_delay_expired_timer_callback = SDL_TIMER_CALLBACK_TYPE(self._on_axes_throttle_delay_expired_timer_callback)

    def init_handlers(self):
        self._event_handlers = {
            sdl2.SDL_QUIT: self._on_quit_event,
            self.AXES_THROTTLE_DELAY_EXPIRED_EVENT: self._on_axes_throttle_delay_expired_event
        }
        if self.device_is_game_controller:
            self._event_handlers.update({
                sdl2.SDL_CONTROLLERDEVICEREMOVED: self._on_device_removed_event,
                sdl2.SDL_CONTROLLERAXISMOTION: self._on_axis_motion_event,
                sdl2.SDL_CONTROLLERBUTTONDOWN: self._on_button_event,
                sdl2.SDL_CONTROLLERBUTTONUP: self._on_button_event
            })
        else:
            self._event_handlers.update({
                sdl2.SDL_JOYDEVICEREMOVED: self._on_device_removed_event,
                sdl2.SDL_JOYAXISMOTION: self._on_axis_motion_event,
                sdl2.SDL_JOYBUTTONDOWN: self._on_button_event,
                sdl2.SDL_JOYBUTTONUP: self._on_button_event
            })

    def event_loop(self):
        assert not self.event_loop_is_running
        self._next_axes_tick = 0
        self._axes_throttle_delay_timer_set = False
        self._last_axes_positions = {axis_idx: None for axis_idx in self.AXIS_MOVEMENT_HANDLERS.keys()}
        self._get_axis_pos = sdl2.SDL_GameControllerGetAxis if self.device_is_game_controller else sdl2.SDL_JoystickGetAxis
        self.event_loop_is_running = True
        try:
            assert SDL_INITED
            assert self.device
            self.init_handlers()
            try:
                while not self.quit_event_posted:
                    event = sdl2.SDL_Event()
                    # If there is no event for an entire second, we iterate, giving CPython an opportunity to
                    # raise KeyboardInterrupt.
                    if sdl2.SDL_WaitEventTimeout(ctypes.byref(event), 1000):
                        self._event_handlers.get(event.type, self._on_unhandled_event)(event)
            except KeyboardInterrupt:
                pass
        finally:
            self.event_loop_is_running = False

    def exit_event_loop(self):
        '''The exit_event_loop method is thread safe and is safe to call even if the event loop is not running.
        Calling exit_event_loop pushes a quit request onto the SDL event queue, causing self.event_loop() to
        exit gracefully (IE, return) if it is running.'''
        event = sdl2.SDL_Event()
        event.type = sdl2.SDL_QUIT
        sdl2.SDL_PushEvent(ctypes.byref(event))

    def _on_quit_event(self, event):
        self.quit_event_posted = True

    def _on_unhandled_event(self, event):
        if self.warnings_enabled:
            print('Received unhandled SDL event: ' + SDL_EVENT_NAMES.get(event.type, "UNKNOWN"), file=sys.stderr)

    @only_for_our_device
    def _on_device_removed_event(self, event):
        self.handle_device_removed()

    def handle_device_removed(self):
        print('Our SDL input device has been disconnected.  Exiting event loop...', sys.stderr)
        self.exit_event_loop()

    @only_for_our_device
    def _on_button_event(self, event):
        if self.device_is_game_controller:
            idx = event.cbutton.button
            state = bool(event.cbutton.state)
        else:
            idx = event.jbutton.button
            state = bool(event.jbutton.state)
        self.handle_button(idx, state)

    def handle_button(self, idx, pressed):
        if idx == sdl2.SDL_CONTROLLER_BUTTON_A:
            # Stop all stage movement when what is typically the gamepad X button is pressed or released
            self.scope.stage.stop_x()
            self.scope.stage.stop_y()
            self.scope.stage.stop_z()

    @only_for_our_device
    def _on_axis_motion_event(self, event):
        # A subtle point: we need to set the axes throttle delay timer only when cooldown has not expired and
        # no timer is set.  That is, if the joystick moves, SDL tells us about it.  When SDL tells us, if we
        # have too recently handled an axis move event, we defer handling the event by setting a timer that wakes
        # us up when the cooldown has expired.  There is never a need to set a new axes throttle delay timer
        # in response to timer expiration.
        curr_ticks = sdl2.SDL_GetTicks()
        if curr_ticks >= self._next_axes_tick:
            self._on_axes_motion()
        else:
            with self._axes_throttle_delay_lock:
                if not self._axes_throttle_delay_timer_set:
                    defer_ticks = round(max(1, self._next_axes_tick - curr_ticks))
                    if not sdl2.SDL_AddTimer(defer_ticks, self._c_on_axes_throttle_delay_expired_timer_callback, ctypes.c_void_p(0)):
                        sdl_e = sdl2.SDL_GetError()
                        sdl_e = sdl_e.decode('utf-8') if sdl_e else 'UNKNOWN ERROR'
                        raise RuntimeError('Failed to set timer: {}'.format(sdl_e))
                    self._axes_throttle_delay_timer_set = True

    def _on_axes_throttle_delay_expired_timer_callback(self, interval, _):
        # NB: SDL timer callbacks execute on a special thread that is not the main thread
        if not self.event_loop_is_running:
            return
        with self._axes_throttle_delay_lock:
            self._axes_throttle_delay_timer_set = False
            if sdl2.SDL_GetTicks() < self._next_axes_tick:
                if self.warnings_enabled:
                    print('Axes throttling delay expiration callback pre-empted.', sys.stderr)
                return 0
        event = sdl2.SDL_Event()
        event.type = self.AXES_THROTTLE_DELAY_EXPIRED_EVENT
        sdl2.SDL_PushEvent(event)
        # Returning 0 tells SDL to not recycle this timer.  _handle_axes_motion, in the main SDL thread, will
        # ultimately be caused to set a new timer by the event we just pushed.
        return 0

    def _on_axes_throttle_delay_expired_event(self, event):
        if sdl2.SDL_GetTicks() < self._next_axes_tick:
            if self.warnings_enabled:
                print('Axes throttling delay expiration event pre-empted.', sys.stderr)
            return
        self._on_axes_motion()

    def _on_axes_motion(self):
        command_ticks = 0
        for axis, cmd in self.AXIS_MOVEMENT_HANDLERS.items():
            pos = self._get_axis_pos(self.device, axis)
            dead_zone = self.AXIS_DEAD_ZONES.get(axis)
            if dead_zone is not None:
                if dead_zone[0] <= pos <= dead_zone[1]:
                    pos = 0
                elif pos < dead_zone[0]:
                    pos -= dead_zone[0]
                elif pos > dead_zone[1]:
                    pos -= dead_zone[1]
            if pos != self._last_axes_positions[axis]:
                demand = pos / (32768 if pos <= 0 else 32767)
                t0 = sdl2.SDL_GetTicks()
                cmd(self, demand)
                t1 = sdl2.SDL_GetTicks()
                self._last_axes_positions[axis] = pos
                command_ticks += t1 - t0
        self._next_axes_tick = sdl2.SDL_GetTicks() + int(min(
            command_ticks * self.throttle_delay_command_time_ratio,
            self.maximum_axis_command_cool_off
        ))

SDL_EVENT_NAMES = {
    sdl2.SDL_APP_DIDENTERBACKGROUND: 'SDL_APP_DIDENTERBACKGROUND',
    sdl2.SDL_APP_DIDENTERFOREGROUND: 'SDL_APP_DIDENTERFOREGROUND',
    sdl2.SDL_APP_LOWMEMORY: 'SDL_APP_LOWMEMORY',
    sdl2.SDL_APP_TERMINATING: 'SDL_APP_TERMINATING',
    sdl2.SDL_APP_WILLENTERBACKGROUND: 'SDL_APP_WILLENTERBACKGROUND',
    sdl2.SDL_APP_WILLENTERFOREGROUND: 'SDL_APP_WILLENTERFOREGROUND',
    sdl2.SDL_CLIPBOARDUPDATE: 'SDL_CLIPBOARDUPDATE',
    sdl2.SDL_CONTROLLERAXISMOTION: 'SDL_CONTROLLERAXISMOTION',
    sdl2.SDL_CONTROLLERBUTTONDOWN: 'SDL_CONTROLLERBUTTONDOWN',
    sdl2.SDL_CONTROLLERBUTTONUP: 'SDL_CONTROLLERBUTTONUP',
    sdl2.SDL_CONTROLLERDEVICEADDED: 'SDL_CONTROLLERDEVICEADDED',
    sdl2.SDL_CONTROLLERDEVICEREMAPPED: 'SDL_CONTROLLERDEVICEREMAPPED',
    sdl2.SDL_CONTROLLERDEVICEREMOVED: 'SDL_CONTROLLERDEVICEREMOVED',
    sdl2.SDL_DOLLARGESTURE: 'SDL_DOLLARGESTURE',
    sdl2.SDL_DOLLARRECORD: 'SDL_DOLLARRECORD',
    sdl2.SDL_DROPFILE: 'SDL_DROPFILE',
    sdl2.SDL_FINGERDOWN: 'SDL_FINGERDOWN',
    sdl2.SDL_FINGERMOTION: 'SDL_FINGERMOTION',
    sdl2.SDL_FINGERUP: 'SDL_FINGERUP',
    sdl2.SDL_FIRSTEVENT: 'SDL_FIRSTEVENT',
    sdl2.SDL_JOYAXISMOTION: 'SDL_JOYAXISMOTION',
    sdl2.SDL_JOYBALLMOTION: 'SDL_JOYBALLMOTION',
    sdl2.SDL_JOYBUTTONDOWN: 'SDL_JOYBUTTONDOWN',
    sdl2.SDL_JOYBUTTONUP: 'SDL_JOYBUTTONUP',
    sdl2.SDL_JOYDEVICEADDED: 'SDL_JOYDEVICEADDED',
    sdl2.SDL_JOYDEVICEREMOVED: 'SDL_JOYDEVICEREMOVED',
    sdl2.SDL_JOYHATMOTION: 'SDL_JOYHATMOTION',
    sdl2.SDL_KEYDOWN: 'SDL_KEYDOWN',
    sdl2.SDL_KEYUP: 'SDL_KEYUP',
    sdl2.SDL_LASTEVENT: 'SDL_LASTEVENT',
    sdl2.SDL_MOUSEBUTTONDOWN: 'SDL_MOUSEBUTTONDOWN',
    sdl2.SDL_MOUSEBUTTONUP: 'SDL_MOUSEBUTTONUP',
    sdl2.SDL_MOUSEMOTION: 'SDL_MOUSEMOTION',
    sdl2.SDL_MOUSEWHEEL: 'SDL_MOUSEWHEEL',
    sdl2.SDL_MULTIGESTURE: 'SDL_MULTIGESTURE',
    sdl2.SDL_QUIT: 'SDL_QUIT',
    sdl2.SDL_RENDER_DEVICE_RESET: 'SDL_RENDER_DEVICE_RESET',
    sdl2.SDL_RENDER_TARGETS_RESET: 'SDL_RENDER_TARGETS_RESET',
    sdl2.SDL_SYSWMEVENT: 'SDL_SYSWMEVENT',
    sdl2.SDL_TEXTEDITING: 'SDL_TEXTEDITING',
    sdl2.SDL_TEXTINPUT: 'SDL_TEXTINPUT',
    sdl2.SDL_WINDOWEVENT: 'SDL_WINDOWEVENT'
}

SDL_CONTROLLER_AXIS_NAMES = {
    sdl2.SDL_CONTROLLER_AXIS_INVALID: 'SDL_CONTROLLER_AXIS_INVALID',
    sdl2.SDL_CONTROLLER_AXIS_LEFTX: 'SDL_CONTROLLER_AXIS_LEFTX',
    sdl2.SDL_CONTROLLER_AXIS_LEFTY: 'SDL_CONTROLLER_AXIS_LEFTY',
    sdl2.SDL_CONTROLLER_AXIS_RIGHTX: 'SDL_CONTROLLER_AXIS_RIGHTX',
    sdl2.SDL_CONTROLLER_AXIS_RIGHTY: 'SDL_CONTROLLER_AXIS_RIGHTY',
    sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT: 'SDL_CONTROLLER_AXIS_TRIGGERLEFT',
    sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT: 'SDL_CONTROLLER_AXIS_TRIGGERRIGHT',
    sdl2.SDL_CONTROLLER_AXIS_MAX: 'SDL_CONTROLLER_AXIS_MAX'
}

SDL_CONTROLLER_BUTTON_NAMES = {
    sdl2.SDL_CONTROLLER_BUTTON_INVALID: 'SDL_CONTROLLER_BUTTON_INVALID',
    sdl2.SDL_CONTROLLER_BUTTON_A: 'SDL_CONTROLLER_BUTTON_A',
    sdl2.SDL_CONTROLLER_BUTTON_B: 'SDL_CONTROLLER_BUTTON_B',
    sdl2.SDL_CONTROLLER_BUTTON_X: 'SDL_CONTROLLER_BUTTON_X',
    sdl2.SDL_CONTROLLER_BUTTON_Y: 'SDL_CONTROLLER_BUTTON_Y',
    sdl2.SDL_CONTROLLER_BUTTON_BACK: 'SDL_CONTROLLER_BUTTON_BACK',
    sdl2.SDL_CONTROLLER_BUTTON_GUIDE: 'SDL_CONTROLLER_BUTTON_GUIDE',
    sdl2.SDL_CONTROLLER_BUTTON_START: 'SDL_CONTROLLER_BUTTON_START',
    sdl2.SDL_CONTROLLER_BUTTON_LEFTSTICK: 'SDL_CONTROLLER_BUTTON_LEFTSTICK',
    sdl2.SDL_CONTROLLER_BUTTON_RIGHTSTICK: 'SDL_CONTROLLER_BUTTON_RIGHTSTICK',
    sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: 'SDL_CONTROLLER_BUTTON_LEFTSHOULDER',
    sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: 'SDL_CONTROLLER_BUTTON_RIGHTSHOULDER',
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP: 'SDL_CONTROLLER_BUTTON_DPAD_UP',
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN: 'SDL_CONTROLLER_BUTTON_DPAD_DOWN',
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT: 'SDL_CONTROLLER_BUTTON_DPAD_LEFT',
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT: 'SDL_CONTROLLER_BUTTON_DPAD_RIGHT',
    sdl2.SDL_CONTROLLER_BUTTON_MAX: 'SDL_CONTROLLER_BUTTON_MAX'
}

SDL_HAT_DIRECTION_NAMES = {
    sdl2.SDL_HAT_LEFTUP: 'SDL_HAT_LEFTUP',
    sdl2.SDL_HAT_UP: 'SDL_HAT_UP',
    sdl2.SDL_HAT_RIGHTUP: 'SDL_HAT_RIGHTUP',
    sdl2.SDL_HAT_LEFT: 'SDL_HAT_LEFT',
    sdl2.SDL_HAT_CENTERED: 'SDL_HAT_CENTERED',
    sdl2.SDL_HAT_RIGHT: 'SDL_HAT_RIGHT',
    sdl2.SDL_HAT_LEFTDOWN: 'SDL_HAT_LEFTDOWN',
    sdl2.SDL_HAT_DOWN: 'SDL_HAT_DOWN',
    sdl2.SDL_HAT_RIGHTDOWN: 'SDL_HAT_RIGHTDOWN'
}

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(epilog='Note: Either device_name/index, --list (-l), or --dump-sdl-input (-d) device_name/index must be supplied.')
    parser.add_argument('--scope', '-s', default='127.0.0.1', help='Hostname or IP address of the scope server.  Defaults to "127.0.0.1".')
    parser.add_argument(
        '--enable-warnings',
        '-w', 
        action='store_true',
        help='Print warnings to stderr when unhandled events are received.')
    parserg = parser.add_mutually_exclusive_group(required=True)
    parserg.add_argument(
        '--list',
        '-l',
        action='store_true',
        help='For each detected SDL joystick and game controller, print a line containing "index, type, joystick name, game controller name".  '
             'The game controller name field is omitted for joysticks that are not also game controllers (all game controllers are joysticks, but '
             'the reverse is not always true).  Then exit.  No connection to the scope server is established.'
    )
    parserg.add_argument(
        '--dump-sdl-input',
        '-d',
        metavar='DEVICE_NAME_OR_INDEX',
        help='Print SDL input from the specified device, formatted for human consumption, to stdout.  Exit gracefully upon '
             'ctrl-c.  Nothing is done with the input aside from printing it to stdout, and no connection to the scope server '
             'is established.'
    )
    parserg.add_argument('device', metavar='DEVICE_NAME_OR_INDEX', nargs='?', help='SDL input device name or index.')
    args = parser.parse_args()
    if args.list:
        for cols in enumerate_devices():
            print(', '.join(str(col) for col in cols))
    elif args.dump_sdl_input is not None:
        if args.dump_sdl_input.isdigit():
            dump_input(input_device_index=int(args.dump_sdl_input))
        else:
            dump_input(input_device_name=args.dump_sdl_input)
    else:
        if args.device.isdigit():
            sdlc = SDLInput(input_device_index=int(args.device), scope_server_host=args.scope)
        else:
            sdlc = SDLInput(input_device_name=args.device, scope_server_host=args.scope)
        sdlc.warnings_enabled = args.enable_warnings
        sdlc.event_loop()
