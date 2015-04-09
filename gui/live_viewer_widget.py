from PyQt5 import Qt

from ris_widget import _ris_widget
from .. import scope_client

class LiveViewerWidget(Qt.QObject):
    # TODO might this better be a subclass of RisWidget?
    RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT = 1001

    @staticmethod
    def can_run(scope):
        return hasattr(scope, 'camera')

    def __init__(self, scope, scope_properties):
        self.ris_widget = _ris_widget.RisWidget()
        super().__init__(self.ris_widget)
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

    def show(self):
        self.ris_widget.show()


#from PyQt5 import Qt
#
#from ris_widget import ris_widget
#from ris_widget import image as ris_widget_image
#from .. import scope_client
#
#class LiveViewerWidget(Qt.QObject):
#    # TODO might this better be a subclass of RisWidget?
#    RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT = 1001
#
#    @staticmethod
#    def can_run(scope):
#        return hasattr(scope, 'camera')
#
#    def __init__(self, scope, scope_properties):
#        self.ris_widget = ris_widget.RisWidget()
#        super().__init__(self.ris_widget)
#        self.live_streamer = scope_client.LiveStreamer(scope, scope_properties, self.post_live_update)
#
#    def event(self, e):
#        # This is called by the main QT event loop to service the event posted in post_live_update().
#        if e.type() == self.RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT:
#            image, frame_no = self.live_streamer.get_image()
#            rwimage = ris_widget_image.Image(image, is_twelve_bit=self.live_streamer.scope.camera.bit_depth=='12 Bit')
#            self.ris_widget.image = rwimage
#            return True
#        return super().event(e)
#
#    def post_live_update(self):
#        # posting an event does not require calling thread to have an event loop,
#        # unlike sending a signal
#        Qt.QCoreApplication.postEvent(self, Qt.QEvent(self.RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT))
#
#    def show(self):
#        self.ris_widget.show()
