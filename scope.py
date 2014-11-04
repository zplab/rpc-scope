from . import messaging
from . import dm6000b
from . import andor
from . import io_tool
from . import spectra_x
from . import tl_lamp

from . import scope_configuration as config

class Scope(messaging.message_device.AsyncDeviceNamespace):
    def __init__(self, property_server, verbose=False):
        super().__init__()
        message_manager = messaging.message_manager.LeicaMessageManager(config.Stand.SERIAL_PORT, config.Stand.SERIAL_BAUD, verbose=verbose)
        
        self.iotool = io_tool.IOTool(config.IOTool.SERIAL_PORT)
        
        self.il = dm6000b.illumination_axes.IL(message_manager, property_server, property_prefix='scope.il.')
        self.il.spectra_x = spectra_x.SpectraX(config.SpectraX.SERIAL_PORT, config.SpectraX.SERIAL_BAUD, 
            iotool, property_server, property_prefix='scope.il.spectra_x.')
        
        self.tl = dm6000b.illumination_axes.TL(message_manager, property_server, property_prefix='scope.tl.')
        self.tl.lamp = tl_lamp.TL_Lamp(iotool, property_server, property_prefix='scope.tl.lamp.')
        
        self.nosepiece = dm6000b.objective_turret.ObjectiveTurret(self._message_manager, property_server, property_prefix='scope.nosepiece.')
        self.stage = dm6000b.stage.Stage(message_manager, property_server, property_prefix='scope.stage.')
        self.stand = dm6000b.stand.Stand(message_manager, property_server, property_prefix='scope.stand.')

        self.camera = andor.camera.Camera(property_server, property_prefix='scope.camera.')
