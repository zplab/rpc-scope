scope_configuration = dict(
    Server = dict(
        LOCALHOST = '127.0.0.1',
        PUBLICHOST = '*',

        RPC_PORT = '6000',
        RPC_INTERRUPT_PORT = '6001',
        PROPERTY_PORT = '6002',
        ASYNC_RPC_PORT = '6003'
    ),

    Stand = dict(
        SERIAL_PORT = '/dev/ttyScope',
        SERIAL_BAUD = 115200,
        INITIALIZE_ALL_OBJECTIVE_LAMP_INTENSITIES_TO_MAXIMUM = True
    ),

    Camera = dict(
        MODEL = 'ZYLA-5.5-USB3'
    ),

    IOTool = dict(
        SERIAL_PORT = '/dev/ttyIOTool',
        LUMENCOR_PINS = dict(
            uv = 'D6',
            blue = 'D5',
            cyan = 'D3',
            teal = 'D4',
            green_yellow = 'D2',
            red = 'D1'
        ),

        CAMERA_PINS = dict(
            trigger = 'B0',
            arm = 'B1',
            fire = 'B2',
            aux_out1 = 'B3'
        ),

        TL_ENABLE_PIN = 'E6',
        TL_PWM_PIN = 'D7',
        TL_PWM_MAX = 255,

        TL_TIMING = dict(
            on_latency_ms = 0, # Time from trigger signal to start of rise
            rise_ms = 0, # Time from start of rise to end of rise
            off_latency_ms = 0, # Time from end of trigger to start of fall
            fall_ms = 0 # Time from start of fall to end of fall
        ),

        SPECTRA_X_TIMING = dict(
            on_latency_ms = 0, # Time from trigger signal to start of rise
            rise_ms = 0, # Time from start of rise to end of rise
            off_latency_ms = 0, # Time from end of trigger to start of fall
            fall_ms = 0 # Time from start of fall to end of fall
        ),

        FOOTPEDAL_PIN = 'B4',
        FOOTPEDAL_CLOSED_TTL_STATE = False,
        FOOTPEDAL_BOUNCE_DELAY_MS = 100
    ),

    SpectraX = dict(
        SERIAL_PORT = '/dev/ttySpectraX',
        SERIAL_BAUD = 9600
    ),

    Peltier = dict(
        SERIAL_PORT = '/dev/ttyPeltier',
        SERIAL_BAUD = 2400
    )
)