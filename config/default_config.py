class Server:
    LOCALHOST = '127.0.0.1'
    PUBLICHOST = '*'

    RPC_PORT = '6000'
    RPC_INTERRUPT_PORT = '6001'
    PROPERTY_PORT = '6002'

class Stand:
    SERIAL_PORT = '/dev/ttyScope'
    SERIAL_BAUD = 115200

class Camera:
    MODEL = 'ZYLA-5.5-CL3'

class IOTool:
    SERIAL_PORT = '/dev/ttyIOTool'
    LUMENCOR_PINS = {
        'uv': 'D6',
        'blue': 'D5',
        'cyan': 'D3',
        'teal': 'D4',
        'green_yellow': 'D2',
        'red': 'D1'
    }

    CAMERA_PINS = {
        'trigger': 'B0',
        'arm': 'B1',
        'fire': 'B2',
        'aux_out1': 'B3'
    }

    TL_ENABLE_PIN = 'E6'
    TL_PWM_PIN = 'D7'
    TL_PWM_MAX = 255

    FOOTPEDAL_PIN = 'B4'
    FOOTPEDAL_CLOSED_TTL_STATE = False
    FOOTPEDAL_BOUNCE_DELAY_MS = 100

class SpectraX:
    SERIAL_PORT = '/dev/ttySpectraX'
    SERIAL_BAUD = 9600

class Peltier:
    SERIAL_PORT = '/dev/ttyPeltier'
    SERIAL_BAUD = 2400
