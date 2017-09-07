# The MIT License (MIT)
#
# Copyright (c) 2014-2015 WUSTL ZPLAB
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Authors: Erik Hvatum <ice.rikh@gmail.com>

import time

from PyQt5 import Qt
from  ris_widget import image
from ris_widget import ris_widget

from .. import scope_client

# TODO: Should live_target be a flipbook entry instead of just self.image?

class ScopeViewerWidget(ris_widget.RisWidgetQtObject):
    NEW_IMAGE_EVENT = Qt.QEvent.registerEventType()
    OVEREXPOSURE_GETCOLOR_EXPRESSION = 's.r < 1.0f ? vec4(s.rrr, 1.0f) : vec4(1.0f, 0.0f, 0.0f, 1.0f)'

    @staticmethod
    def can_run(scope):
        return hasattr(scope, 'camera')

    def __init__(self, scope, scope_properties, window_title='Viewer', fps_max=None, app_prefs_name='scope-viewer', parent=None):
        super().__init__(window_title=window_title, app_prefs_name=app_prefs_name, parent=parent)

        self.main_view_toolbar.removeAction(self.snapshot_action)
        self.dock_widget_visibility_toolbar.removeAction(self.layer_stack_painter_dock_widget.toggleViewAction())

        self.scope_toolbar = self.addToolBar('Scope')
        self.show_over_exposed_action = Qt.QAction('Show Over-Exposed Live Pixels', self)
        self.show_over_exposed_action.setCheckable(True)
        self.show_over_exposed_action.setChecked(False)
        self.show_over_exposed_action.toggled.connect(self.on_show_over_exposed_action_toggled)
        self.show_over_exposed_action.setChecked(True)
        self.scope_toolbar.addAction(self.show_over_exposed_action)
        self.closing = False
        self.live_streamer = scope_client.LiveStreamer(scope, scope_properties, self.post_new_image_event)
        if fps_max is None:
            self.interval_min = None
        else:
            self.interval_min = 1/fps_max
        self.last_image = 0

    def closeEvent(self, e):
        self.closing = True
        self.live_streamer.detach()
        super().closeEvent(e)

    def event(self, e):
        # This is called by the main QT event loop to service the event posted in post_new_image_event().
        if e.type() == self.NEW_IMAGE_EVENT and self.live_streamer.image_ready():
            if self.interval_min is not None:
                t = time.time()
                if t - self.last_image < self.interval_min:
                    return True
                self.last_image = t
            image_data, timestamp, frame_no = self.live_streamer.get_image()
            image_bits = 12 if self.live_streamer.bit_depth == '12 Bit' else 16
            self.image = image.Image(image_data, image_bits=image_bits)
            if self.show_over_exposed_action.isChecked() and self.layer.image.type == 'G':
                self.layer.getcolor_expression = self.OVEREXPOSURE_GETCOLOR_EXPRESSION
            else:
                del self.layer.getcolor_expression
            return True
        return super().event(e)

    def post_new_image_event(self):
        # posting an event does not require calling thread to have an event loop,
        # unlike sending a signal
        if not self.closing and self.isVisible():
            Qt.QCoreApplication.postEvent(self, Qt.QEvent(self.NEW_IMAGE_EVENT))

    def on_show_over_exposed_action_toggled(self, show_over_exposed):
        if show_over_exposed:
            if self.layer.image is not None and self.layer.image.type == 'G':
                self.layer.getcolor_expression = self.OVEREXPOSURE_GETCOLOR_EXPRESSION
        else:
            # Revert to default getcolor_expression
            del self.layer.getcolor_expression

