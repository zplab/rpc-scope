# This code is licensed under the MIT License (see LICENSE file for details)

from ris_widget import shared_resources

from .. import scope_client
from . import scope_widgets
from . import andor_camera_widget
from . import lamp_widget
from . import scope_viewer_widget
from . import microscope_widget
from . import game_controller_input_widget
from . import incubator_widget

WIDGETS = [
    # properties not specified as True are assumed False
    dict(name='camera', cls=andor_camera_widget.AndorCameraWidget, start_visible=True, docked=True),
    dict(name='advanced_camera', cls=andor_camera_widget.AndorAdvancedCameraWidget, pad=True),
    dict(name='lamps', cls=lamp_widget.LampWidget, start_visible=True, docked=True),
    dict(name='incubator', cls=incubator_widget.IncubatorWidget, start_visible=True, docked=True),
    dict(name='microscope', cls=microscope_widget.MicroscopeWidget, start_visible=True, docked=True),
    dict(name='viewer', cls=scope_viewer_widget.ScopeViewerWidget, start_visible=True),
    dict(name='game_controller', cls=game_controller_input_widget.GameControllerInputWidget)
]

def gui_main(host):
    shared_resources.init_qapplication(icon_resource_path=(__name__, 'icon.svg'))
    scope = scope_client.ScopeClient(host)
    title = "Microscope Control"
    if host not in {'localhost', '127.0.0.1'}:
        title += ': {}'.format(host)
    main_window = scope_widgets.WidgetWindow(scope, WIDGETS, window_title=title)
    shared_resources.run_qapplication()

def monitor_main(hosts, downsample=None, fps_max=None):
    shared_resources.init_qapplication(icon_resource_path=(__name__, 'icon.svg'))
    viewers = []
    for host in hosts:
        scope = scope_client.ScopeClient(host, allow_interrupt=False, auto_connect=False)
        app_prefs_name = 'viewer-{}'.format(host)
        viewer = scope_viewer_widget.MonitorWidget(scope, host, downsample, fps_max, app_prefs_name)
        viewers.append(viewer)
    shared_resources.run_qapplication()
