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

WIDGET_NAMES = set(widget['name'] for widget in WIDGETS)

def gui_main(host, desired_widgets=None):
    app = shared_resources.init_qapplication(icon_resource_path=None)
    scope, scope_properties = scope_client.client_main(host)
    if desired_widgets is None:
        widgets = WIDGETS
    else:
        desired_widgets = set(desired_widgets)
        for widget in desired_widgets:
            if not widget in WIDGET_NAMES:
                raise ValueError('Unknown GUI widget "{}"'.format(widget))
            # keep widget order from WIDGETS list
            widgets = [widget for widget in WIDGETS if widget['name'] in desired_widgets]

    title = "Microscope Control"
    if host not in {'localhost', '127.0.0.1'}:
        title += ': {}'.format(host)
    main_window = scope_widgets.WidgetWindow(scope, scope_properties, widgets, window_title=title)
    main_window.show()
    app.exec()

def monitor_main(hosts, downsample=None, fps_max=None):
    app = shared_resources.init_qapplication(icon_resource_path=None)
    viewers = []
    for host in hosts:
        scope, scope_properties = scope_client.client_main(host)
        if hasattr(scope, 'camera'):
            if not scope._is_local:
                scope._get_data.downsample = downsample
            app_prefs_name = 'viewer-{}'.format(host)
            viewer = scope_viewer_widget.MonitorWidget(scope, scope_properties, host, fps_max, app_prefs_name)
            viewer.show()
            viewers.append(viewer)
    app.exec()
