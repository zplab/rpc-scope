# This code is licensed under the MIT License (see LICENSE file for details)

import time
import datetime
import numpy
from PyQt5 import Qt

from ris_widget import image
from ris_widget import ris_widget
import freeimage

from . import status_widget
from .. import scope_client
from .. import util

# TODO: Should live_target be a flipbook entry instead of just self.image?

class ScopeViewerWidget(ris_widget.RisWidgetQtObject):
    NEW_IMAGE_EVENT = Qt.QEvent.registerEventType()
    OVEREXPOSURE_GETCOLOR_EXPRESSION = 's.r < 1.0f ? vec4(s.rrr, 1.0f) : vec4(1.0f, 0.0f, 0.0f, 1.0f)'

    @staticmethod
    def can_run(scope):
        return hasattr(scope, 'camera')

    def __init__(self, scope, window_title='Viewer', fps_max=None, app_prefs_name='scope-viewer', parent=None):
        super().__init__(window_title=window_title, app_prefs_name=app_prefs_name, parent=parent)
        self.scope = scope

        self.main_view_toolbar.removeAction(self.snapshot_action)

        self.scope_toolbar = self.addToolBar('Scope')
        self.show_over_exposed_action = Qt.QAction('Show Over-Exposed', self)
        self.show_over_exposed_action.setCheckable(True)
        self.show_over_exposed_action.setChecked(True)
        self.show_over_exposed_action.toggled.connect(self.on_show_over_exposed_action_toggled)
        self.scope_toolbar.addAction(self.show_over_exposed_action)

        self.flipbook.pages.append(image.Image(numpy.array([[0]], dtype=numpy.uint8), name='Live Image'))
        self.live_image_page = self.flipbook.pages[-1]
        self.flipbook_dock_widget.hide()
        self.image = None

        self.snap_action = Qt.QAction('Snap Image', self)
        self.snap_action.triggered.connect(self.snap_image)
        self.scope_toolbar.addAction(self.snap_action)

        self.save_action = Qt.QAction('Save Image', self)
        self.save_action.triggered.connect(self.save_image)
        self.scope_toolbar.addAction(self.save_action)

        self.servicing_image = util.Condition()
        self.closing = False
        if fps_max is None:
            self.interval_min = None
        else:
            self.interval_min = 1/fps_max
        self.last_image_time = 0
        self.live_streamer = scope_client.LiveStreamer(scope, self.post_new_image_event)


    def closeEvent(self, e):
        if self.closing:
            # sometimes closeEvent gets fired off twice (2018-01, PyQt 5.9). Why? TODO: verify if problem goes away in later Qt
            return
        self.closing = True
        self.live_streamer.detach()
        super().closeEvent(e)

    def event(self, e):
        # This is called by the main QT event loop to service the event posted in post_new_image_event().
        if e.type() == self.NEW_IMAGE_EVENT:
            with self.servicing_image:
                if self.interval_min is not None:
                    t = time.time()
                    if t - self.last_image_time < self.interval_min:
                        return True
                try:
                    image_data, timestamp, frame_number = self.live_streamer.get_image(timeout=4)
                except scope_client.LiveStreamer.Timeout:
                    return True
                self.last_image_time = time.time()
                bit_depth = int(self.live_streamer.bit_depth[:2])
                image_obj = image.Image(image_data, image_bits=bit_depth)
                if self.show_over_exposed_action.isChecked() and image_obj.type == 'G':
                    self.layer.getcolor_expression = self.OVEREXPOSURE_GETCOLOR_EXPRESSION
                else:
                    del self.layer.getcolor_expression
                self.live_image_page[0] = image_obj
                return True
        return super().event(e)

    def post_new_image_event(self):
        # posting an event does not require calling thread to have an event loop,
        # unlike sending a signal
        if not self.servicing_image and not self.closing and self.isVisible():
            Qt.QCoreApplication.postEvent(self, Qt.QEvent(self.NEW_IMAGE_EVENT))

    def on_show_over_exposed_action_toggled(self, show_over_exposed):
        if show_over_exposed:
            if self.layer.image is not None and self.layer.image.type == 'G':
                self.layer.getcolor_expression = self.OVEREXPOSURE_GETCOLOR_EXPRESSION
        else:
            # Revert to default getcolor_expression
            del self.layer.getcolor_expression

    def snap_image(self):
        self.flipbook.pages.append_named(self.scope.camera.acquire_image(), datetime.datetime.now().isoformat(' ', 'seconds'))
        self.flipbook.current_page_idx = -1

    def save_image(self):
        fn, _ = Qt.QFileDialog.getSaveFileName(self, 'Save Image', self.flipbook.current_page.name+'.png', filter='Images (*.png *.tiff *.tif)')
        if fn:
            freeimage.write(self.image.data, fn)

class MonitorWidget(ScopeViewerWidget):
    def __init__(self, scope, window_title='Viewer', downsample=None, fps_max=None, app_prefs_name='scope-viewer', parent=None):
        super().__init__(scope, window_title, fps_max, app_prefs_name, parent)
        self.live_streamer.image_ready_callback = None # don't allow image callbacks until scope is connected
        self.downsample = downsample
        self.removeToolBar(self.scope_toolbar)
        self.show_over_exposed_action.setChecked(False)
        self.histogram_dock_widget.hide()
        self.image_view.zoom_to_fit_action.setChecked(False)
        self.main_view_toolbar.removeAction(self.layer_stack.solo_layer_mode_action)
        self.dock_widget_visibility_toolbar.removeAction(self.layer_table_dock_widget.toggleViewAction())
        self.dock_widget_visibility_toolbar.removeAction(self.flipbook_dock_widget.toggleViewAction())
        new_central = Qt.QWidget()
        vbox = Qt.QVBoxLayout(new_central)
        vbox.setContentsMargins(0,3,0,0)
        vbox.setSpacing(3)
        status = status_widget.StatusWidget(scope)
        status.layout().insertSpacing(0, 5)
        vbox.addWidget(status)
        vbox.addWidget(self.centralWidget())
        self.setCentralWidget(new_central)
        self.show()
        self.timer = Qt.QBasicTimer()
        self.timer.start(10000, Qt.Qt.VeryCoarseTimer, self) # run self.timerEvent every 10 sec until scope connection achieved
        self.timerEvent(None)

    def timerEvent(self, event):
        if not self.scope._can_connect():
            return
        if not self.scope._is_connected():
            self.scope._connect()
        self.timer.stop()
        if not self.scope._is_local:
            self.scope._get_data.downsample = self.downsample
        self.live_streamer.image_ready_callback = self.post_new_image_event
        self.scope.rebroadcast_properties()
