import signal

from PyQt5 import Qt
import threading

from .. import scope_client
from .. util import sdl_input

def sigint_handler(*args):
    """Handler for the SIGINT signal."""
    Qt.QApplication.quit()

def gui_main(host, **widget_classes):
    params = []
    Qt.QApplication.setAttribute(Qt.Qt.AA_ShareOpenGLContexts)
    app = Qt.QApplication(params)

    scope, scope_properties = scope_client.client_main(host)
    widget_namespace = make_and_show_widgets(scope, scope_properties, **widget_classes)

    if sdl_input.enumerate_devices():
        sdl_input_instance = sdl_input.SDLInput(scope_server_host=host)
        sdl_input_thread = threading.Thread(target=sdl_input_instance.event_loop)
        sdl_input_thread.start()
        app.aboutToQuit.connect(sdl_input_instance.exit_event_loop)

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

class WidgetNamespace:
    pass

def make_and_show_widgets(scope, scope_properties, **widget_classes):
    widget_namespace = WidgetNamespace()
    widgets = []
    for name, wc in widget_classes.items():
        if wc.can_run(scope):
            w = wc(scope=scope, scope_properties=scope_properties)
            widgets.append(w)
            setattr(widget_namespace, name, w)
        else:
            print('Scope cannot currently run {}. (Hardware not turned on?)'.format(name))
    scope.rebroadcast_properties()
    for widget in widgets:
        widget.show()
    return widget_namespace

def make_and_show_all_widgets(scope, scope_properties):
    from ..cli.scope_gui import WIDGETS
    return make_and_show_widgets(scope, scope_properties, **WIDGETS)
