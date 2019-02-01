scope_configuration = dict(
    drivers = ( # order is important!
        ('stand', 'leica.stand.Stand'),
        ('stage', 'leica.stage.Stage'),
        #('nosepiece', 'leica.nosepiece.MotorizedNosepieceWithSafeMode'), # dm6000
        #('nosepiece', 'leica.nosepiece.MotorizedNosepiece'), # dmi8
        #('nosepiece', 'leica.nosepiece.ManualNosepiece'), # dm6
        #('il', 'leica.illumination_axes.IL'), # dmi8
        #('il', 'leica.illumination_axes.FieldWheel_IL'), # dm6000 dm6
        #('tl', 'leica.illumination_axes.TL'), # dm6000 dm6
        #('_shutter_watcher', 'leica.illumination_axes.ShutterWatcher'), # dm6000 dm6
        ('iotool', 'iotool.IOTool'),
        #('il.spectra', 'spectra.Spectra'), # dm6
        #('il.spectra', 'spectra.SpectraX'), # dm6000 dmi8
        ('tl.lamp', 'tl_lamp.SutterLED_Lamp'),
        # ('camera', 'andor.Zyla'),
        # ('camera', 'andor.Sona'),
        ('camera.acquisition_sequencer', 'acquisition_sequencer.AcquisitionSequencer'),
        ('camera.autofocus', 'autofocus.Autofocus'),
        #('temperature_controller', 'temp_control.Peltier'), # dm6000
        #('temperature_controller', 'temp_control.Circulator'), # dm6
        #('humidity_controller', 'humidity_control.HumidityController'), # dm6, dm6000
        ('job_runner', 'runner_device.JobRunner')
    ),

    server = dict(
        LOCALHOST = '127.0.0.1',
        PUBLICHOST = '*',
        RPC_PORT = '6000',
        RPC_INTERRUPT_PORT = '6001',
        PROPERTY_PORT = '6002',
        IMAGE_TRANSFER_RPC_PORT = '6003',
    ),

    stand = dict(
        SERIAL_PORT = '/dev/ttyScope',
        SERIAL_ARGS = dict(
            baudrate = 115200
        ),
        TL_FIELD_DEFAULTS = {
            #'5': 12, # dm6
            #'5': 10, # dm6000
            #'10': 16 # dm6
            #'10': 18 # dm6000
        },
        TL_APERTURE_DEFAULTS = {
            '5': 28, # dm6, dm6000
            #'10': 26 # dm6
            #'10': 22 # dm6000
        }
    ),

    camera = dict(
        IOTOOL_PINS = dict(
            trigger = 'B0',
            arm = 'B1',
            aux_out1 = 'B2'
        ),
    ),

    iotool = dict(
        SERIAL_PORT = '/dev/ttyIOTool',
        SERIAL_ARGS = dict(
            baudrate=115200
        )
    ),

    spectra = dict(
        SERIAL_PORT = '/dev/ttySpectra',
        SERIAL_ARGS = {},
        IOTOOL_LAMP_PINS = dict(
            uv = 'D6',
            blue = 'D5',
            cyan = 'D3',
            teal = 'D4',
            green_yellow = 'D2',
            #red = 'D1' # dm6000 dmi8
        ),
        #IOTOOL_GREEN_YELLOW_SWITCH_PIN = 'D1', # dm6

        # TIMING: depends *strongly* on how recently the last time the
        # lamp was turned on was. 100 ms ago vs. 10 sec ago changes the on-latency
        # by as much as 100 us.
        # Some lamps have different rise times vs. latencies.
        # All lamps have ~6 us off latency and 9-13 us fall.
        # With 100 ms delay between off and on:
        # Lamp    On-Latency  Rise    Off-Latency  Fall
        # Red     90 us       16 us   6 us         11 us
        # Green   83          19      10           13
        # Cyan    96          11      6            9
        # UV      98          11      6            11
        #
        # With 5 sec delay, cyan and green on-latency goes to 123 usec.
        # With 20 sec delay, it is at 130 us.
        # Plug in sort-of average values below, assuming 5 sec delay:
        TIMING = dict(
            on_latency_ms = 0.120, # Time from trigger signal to start of rise
            rise_ms = 0.015, # Time from start of rise to end of rise
            off_latency_ms = 0.01, # Time from end of trigger to start of fall
            fall_ms = 0.015 # Time from start of fall to end of fall
        ),
        #FILTER_SWITCH_DELAY = 0.15 # dm6
    ),

    sutter_led = dict(
        IOTOOL_ENABLE_PIN = 'E6',
        IOTOOL_PWM_PIN = 'D0',
        IOTOOL_PWM_MAX = 255,
        INITIAL_INTENSITY = 86,
        TIMING = dict(
            on_latency_ms = 0.025, # Time from trigger signal to start of rise
            rise_ms = 0.06, # Time from start of rise to end of rise
            off_latency_ms = 0.06, # Time from end of trigger to start of fall
            fall_ms = 0.013 # Time from start of fall to end of fall
        ),
    ),

    # peltier = dict(
    #     SERIAL_PORT = '/dev/ttyPeltier',
    #     SERIAL_ARGS = dict(
    #         baudrate = 2400
    #     )
    # ),
    #
    # circulator = dict(
    #     SERIAL_PORT = '/dev/ttyCirculator',
    #     SERIAL_ARGS = dict(
    #         baudrate=9600
    #     )
    # ),
    #
    # humidifier = dict(
    #     SERIAL_PORT = '/dev/ttyHumidifier',
    #     SERIAL_ARGS = dict(
    #         baudrate=19200
    #     )
    # ),
    mail_relay = 'osmtp.wustl.edu'
)
