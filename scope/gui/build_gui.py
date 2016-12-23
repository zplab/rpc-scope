import signal

import OpenGL
OpenGL.ERROR_CHECKING = False

from PyQt5 import Qt

from .. import scope_client
from . import scope_widgets
from . import andor_camera_widget
from . import lamp_widget
from . import scope_viewer_widget
from . import microscope_widget
from . import stage_pos_table_widget
from . import joypad_input_widget

WIDGETS = [
    dict(name='camera', cls=andor_camera_widget.AndorCameraWidget, start_visible=True, docked=True),
    dict(name='lamps', cls=lamp_widget.LampWidget, start_visible=True, docked=True),
    dict(name='microscope', cls=microscope_widget.MicroscopeWidget, start_visible=True, docked=True),
    dict(name='game_controller', cls=joypad_input_widget.JoypadInputWidget, start_visible=True, docked=True),
    dict(name='advanced_camera', cls=andor_camera_widget.AndorAdvancedCameraWidget, start_visible=False, docked=True),
    dict(name='viewer', cls=scope_viewer_widget.ScopeViewerWidget, start_visible=True, docked=False),
    dict(name='stage_table', cls=stage_pos_table_widget.StagePosTableWidget, start_visible=False, docked=False)
]

WIDGET_NAMES = set(widget['name'] for widget in WIDGETS)

def sigint_handler(*args):
    """Handler for the SIGINT signal."""
    Qt.QApplication.quit()

def gui_main(host, desired_widgets=None):
    Qt.QApplication.setAttribute(Qt.Qt.AA_ShareOpenGLContexts)
    app = Qt.QApplication([])

    scope, scope_properties = scope_client.client_main(host)
    if widgets is None:
        widgets = WIDGETS
    else:
        desired_widgets = set(desired_widgets)
        for widget in desired_widgets:
            if not widget in WIDGET_NAMES:
                raise ValueError('Unknown GUI widget "{}"'.format(widget))
            # keep widget order from WIDGETS list
            widgets = [widget for widget in WIDGETS if widget['name'] in desired_widgets]

    main_window = scope_widgets.WidgetWindow(
        host=host,
        scope=scope,
        scope_properties=scope_properties,
        widgets=widgets
    )
    main_window.show()

    # install a custom signal handler so that when python receives control-c, QT quits
    signal.signal(signal.SIGINT, sigint_handler)
    # now arrange for the QT event loop to allow the python interpreter to
    # run occasionally. Otherwise it never runs, and hence the signal handler
    # would never get called.
    timer = Qt.QTimer()
    timer.start(100)
    # add a no-op callback for timeout. What's important is that the python interpreter
    # gets a chance to run so it can see the signal and call the handler.
    timer.timeout.connect(lambda: None)

    app.exec()