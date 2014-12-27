import signal
from PyQt5 import Qt

from ris_widget import _ris_widget
from . import scope_client

def sigint_handler(*args):
    """Handler for the SIGINT signal."""
    Qt.QApplication.quit()

def make_streamer(host=None, ris_widget=None):
    scope, scope_properties = scope_client.client_main(host)
    if ris_widget is None:
        ris_widget = _ris_widget.RisWidget()
        ris_widget.show()
    streamer = RisWidgetStreamer(ris_widget, scope, scope_properties)
    return streamer

def streamer_main(host=None):
    params = []
    app = Qt.QApplication(params)
    streamer = make_streamer(host)

    # install a custom signal handler so that when python receives control-c,
    # QT quits
    # TODO: bundle this up into some code in the gui module, so that other
    # GUI widgets behave similarly
    signal.signal(signal.SIGINT, sigint_handler)
    # now arrange for the QT event loop to allow the python interpreter to
    # run occasionally. Otherwise it never runs, and hence the signal handler
    # would never get called.
    timer = Qt.QTimer()
    timer.start(100)
    # add a no-op callback for timeout. What's important is that the interpreter
    # runs, so it can see the signal and call the handler.
    timer.timeout.connect(lambda: None)

    app.exec()

class RisWidgetStreamer(Qt.QObject):
    RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT = 1001

    def __init__(self, ris_widget, scope, scope_properties):
        super().__init__(ris_widget)
        self.ris_widget = ris_widget
        self.live_streamer = scope_client.LiveStreamer(scope, scope_properties, self.post_live_update)

    def event(self, e):
        # This is called by the main QT event loop to service the event posted in post_live_update().
        if e.type() == self.RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT:
            image, frame_no = self.live_streamer.get_image()
            self.ris_widget.showImage(image)
            return True
        return super().event(e)

    def post_live_update(self):
        # posting an event does not require calling thread to have an event loop,
        # unlike sending a signal
        Qt.QCoreApplication.postEvent(self, Qt.QEvent(self.RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT))

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Show a live-view window from the microscope camera")
    parser.add_argument("--host", help="Host computer to connect to [defaults to localhost]")
    args = parser.parse_args()
    streamer_main(args.host)