from .camera_base import Camera, AndorProp

class Zyla(Camera):
    _DESCRIPTION = 'Andor Zyla'
    _MODEL_NAME = 'ZYLA-5.5-USB3'
    _CAMERA_PROPERTIES = dict(Camera._CAMERA_PROPERTIES,
        readout_rate = AndorProp('PixelReadoutRate', 'Enum', default='100 MHz'),
        sensor_cooling_target = AndorProp('TemperatureControl', 'Enum', readonly=True),
        sensor_gain = AndorProp('SimplePreAmpGainControl', 'Enum', default='16-bit (low noise & high well capacity)'),
        shutter_mode = AndorProp('ElectronicShutteringMode', 'Enum', default='Rolling'),
        static_blemish_correction_enabled = AndorProp('StaticBlemishCorrection', 'Bool', default=True),
    )
    _HIDDEN_PROPERTIES = Camera._HIDDEN_PROPERTIES + (
        AndorProp('AccumulateCount', 'Int', default=1)
    )
    _GAIN_TO_ENCODING = {
        '12-bit (high well capacity)': 'Mono12Packed',
        '12-bit (low noise)': 'Mono12Packed',
        '16-bit (low noise & high well capacity)': 'Mono16'
    }
    _IO_PINS = [
        'Fire 1',
        'Fire N',
        'Aux Out 1',
        'Arm',
        'External Trigger'
    ]
    _BASIC_PROPERTIES = [ # minimal set of properties to concern oneself with (e.g. from a GUI)
        'live_mode',
        'is_acquiring',
        'temperature_status',
        'sensor_temperature',
        'exposure_time',
        'binning',
        'aoi_left',
        'aoi_top',
        'aoi_width',
        'aoi_height',
        'sensor_gain',
        'readout_rate',
        'overlap_enabled',
        'cycle_mode',
        'frame_count',
        'frame_rate',
        'frame_rate_range',
        'max_interface_fps',
        'readout_time',
        'trigger_mode'
    ]


class Sona(Camera):
    _DESCRIPTION = 'Andor Sona'
    _MODEL_NAME = 'SONA-4.2-USB3'
    _CAMERA_PROPERTIES = dict(Camera._CAMERA_PROPERTIES,
        family_name = AndorProp('CameraFamily', 'String', readonly=True),
        readout_rate = AndorProp('PixelReadoutRate', 'Enum', readonly=True),
        sensor_cooling_target = AndorProp('TemperatureControl', 'Enum', default='-25.0', readonly=True),
        sensor_gain = AndorProp('GainMode', 'Enum', default='High dynamic range (16-bit)'),
        shutter_mode = AndorProp('ElectronicShutteringMode', 'Enum', readonly=True),
    )
    _GAIN_TO_ENCODING = {
        'Fastest frame rate (12-bit)': 'Mono12Packed',
        'High dynamic range (16-bit)': 'Mono16'
    }
    _IO_PINS = [
        'Fire 1',
        'Fire N',
        'Aux Out 1',
        'Aux Out 2',
        'Arm',
        'External Trigger',
        'External Exposure',
        'Spare Input'
    ]
    _BASIC_PROPERTIES = [ # minimal set of properties to concern oneself with (e.g. from a GUI)
        'live_mode',
        'is_acquiring',
        'temperature_status',
        'sensor_temperature',
        'exposure_time',
        'binning',
        'aoi_left',
        'aoi_top',
        'aoi_width',
        'aoi_height',
        'sensor_gain',
        'overlap_enabled',
        'cycle_mode',
        'frame_count',
        'frame_rate',
        'frame_rate_range',
        'max_interface_fps',
        'readout_time',
        'trigger_mode'
    ]
