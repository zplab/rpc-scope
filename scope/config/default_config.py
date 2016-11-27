scope_configuration = dict(
    scope_components = (
        ('stand', 'leica.stand.Stand'),
        ('stage', 'leica.stage.Stage'),
        ('nosepiece', 'nosepiece.Nosepiece'), # dm6000 dmi8
        #('nosepiece', 'nosepiece.ManualNosepiece'), # dm6
        #('il', 'leica.illumination_axes.IL'), # dmi8
        ('il', 'leica.illumination_axes.FieldWheel_IL'), # dm6000 dm6
        ('tl', 'leica.illumination_axes.TL'),
        ('_shutter_watcher', 'leica.illumination_axes.ShutterWatcher'), # dm6000 dm6
        ('iotool', 'iotool.IOTool'),
        ('il.spectra', 'spectra.Spectra'),
        ('tl.lamp', 'tl_lamp.SutterLED_Lamp'),
        ('camera', 'andor.Camera'),
        ('camera.acquisition_sequencer', 'acquisition_sequencer.AcquisitionSequencer'),
        ('camera.autofocus', 'autofocus.Autofocus'),
        ('temperature_controller', 'temp_control.Peltier') # dm6000
        #('temperature_controller', 'temp_control.Chiller') # dm6
    ),

    server = dict(
        LOCALHOST = '127.0.0.1',
        PUBLICHOST = '*',

        RPC_PORT = '6000',
        RPC_INTERRUPT_PORT = '6001',
        PROPERTY_PORT = '6002',
        IMAGE_TRANSFER_RPC_PORT = '6003'
    ),

    stand = dict(
        SERIAL_PORT = '/dev/ttyScope',
        SERIAL_BAUD = 115200,
    ),

    nosepiece = dict(
        HAS_SAFE_MODE = True # dm6000
        #HAS_SAFE_MODE = False # dmi8 dm6
    ),

    camera = dict(
        MODEL = 'ZYLA-5.5-USB3'
    ),

    iotool = dict(
        SERIAL_PORT = '/dev/ttyIOTool',
        LUMENCOR_PINS = dict(
            uv = 'D6',
            blue = 'D5',
            cyan = 'D3',
            teal = 'D4',
            green_yellow = 'D2',
            red = 'D1' # dm6000 dmi8
            # switch_green_yellow = 'D1' # dm6
        ),

        CAMERA_PINS = dict(
            trigger = 'B0',
            arm = 'B1',
            aux_out1 = 'B2'
        ),

        TL_ENABLE_PIN = 'E6',
        TL_PWM_PIN = 'D0',
        TL_PWM_MAX = 255,

        TL_TIMING = dict(
            on_latency_ms = 0.025, # Time from trigger signal to start of rise
            rise_ms = 0.06, # Time from start of rise to end of rise
            off_latency_ms = 0.06, # Time from end of trigger to start of fall
            fall_ms = 0.013 # Time from start of fall to end of fall
        ),

        # SPECTRA_TIMING: depends *strongly* on how recently the last time the
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
        SPECTRA_TIMING = dict(
            on_latency_ms = .120, # Time from trigger signal to start of rise
            rise_ms = .015, # Time from start of rise to end of rise
            off_latency_ms = 0.08, # Time from end of trigger to start of fall
            fall_ms = .010 # Time from start of fall to end of fall
        ),
    ),

    spectra = dict(
        SERIAL_PORT = '/dev/ttySpectra',
        SERIAL_BAUD = 9600
    ),

    peltier = dict(
        SERIAL_PORT = '/dev/ttyPeltier',
        SERIAL_BAUD = 2400
    )

    circulator = dict(
        SERIAL_PORT = '/dev/ttyCirculator',
        SERIAL_BAUD = ???
    )

)
