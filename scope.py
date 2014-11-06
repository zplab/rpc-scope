from serial import SerialException
import traceback

from . import messaging
from . import dm6000b
from . import andor
from . import io_tool
from . import spectra_x
from . import tl_lamp

from . import scope_configuration as config

def _print_exception(preamble, e):
    exception_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
    print(preamble + '\n' + exception_str)

class Namespace:
    pass

class Scope(messaging.message_device.AsyncDeviceNamespace):
    def __init__(self, property_server, verbose=False):
        super().__init__()
        
        if property_server:
            self.rebroadcast_properties = property_server.rebroadcast_properties
        
        try:
            message_manager = messaging.message_manager.LeicaMessageManager(config.Stand.SERIAL_PORT, config.Stand.SERIAL_BAUD, verbose=verbose)
        except SerialException as e:
            message_manager = None
            _print_exception('Could not connect to microscope:', e)
        
        if message_manager:
            self.nosepiece = dm6000b.objective_turret.ObjectiveTurret(message_manager, property_server, property_prefix='scope.nosepiece.')
            self.stage = dm6000b.stage.Stage(message_manager, property_server, property_prefix='scope.stage.')
            self.stand = dm6000b.stand.Stand(message_manager, property_server, property_prefix='scope.stand.')
            self.il = dm6000b.illumination_axes.IL(message_manager, property_server, property_prefix='scope.il.')
            self.tl = dm6000b.illumination_axes.TL(message_manager, property_server, property_prefix='scope.tl.')

        try:
            print('doing self.iotool = io_tool.IOTool(config.IOTool.SERIAL_PORT)')
            self.iotool = io_tool.IOTool(config.IOTool.SERIAL_PORT)
            has_iotool = True
        except SerialException as e:
            has_iotool = False
            _print_exception('Could not connect to IOTool box:', e)
        finally:
            print('did self.iotool = io_tool.IOTool(config.IOTool.SERIAL_PORT)')
        
        if not message_manager and has_iotool:
            self.il = Namespace()
            self.tl = Namespace()
        if has_iotool:
            self.il.spectra_x = spectra_x.SpectraX(config.SpectraX.SERIAL_PORT, config.SpectraX.SERIAL_BAUD, 
                self.iotool, property_server, property_prefix='scope.il.spectra_x.')
            self.tl.lamp = tl_lamp.TL_Lamp(self.iotool, property_server, property_prefix='scope.tl.lamp.')
        
        try:
            self.camera = andor.camera.Camera(property_server, property_prefix='scope.camera.')
        except andor.lowlevel.AndorError as e:
            _print_exception('Could not connect to camera:', e)
            
