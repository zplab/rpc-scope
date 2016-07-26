import signal

from PyQt5 import Qt

from .. import scope_client
from . import scope_widgets

def sigint_handler(*args):
    """Handler for the SIGINT signal."""
    Qt.QApplication.quit()

def gui_main(host, names_of_desired_widgets):
    params = []
    Qt.QApplication.setAttribute(Qt.Qt.AA_ShareOpenGLContexts)
    app = Qt.QApplication(params)

    scope, scope_properties = scope_client.client_main(host)
    main_window = scope_widgets.WidgetWindow(
        host=host,
        scope=scope,
        scope_properties=scope_properties,
        names_of_desired_widgets=names_of_desired_widgets
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