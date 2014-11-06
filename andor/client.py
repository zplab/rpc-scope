# The MIT License (MIT)
#
# Copyright (c) 2014 WUSTL ZPLAB
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
# Authors: Erik Hvatum, Zach Pincus

#ipython -i -c 'import zmq;context=zmq.Context();from rpc_acquisition import scope_server;client, scope = scope_server.rpc_client_main(context=context);prop_client = scope_server.property_client_main(context=context)'

#from ris_widget._ris_widget import RisWidget;rw=RisWidget();rw.show()
#from rpc_acquisition.andor.client import ZMQAndorImageClient
#zaic = ZMQAndorImageClient(context)
#newest_andor_image = None
#def new_andor_image_received(andor_image):
#    global newest_andor_image
#    newest_andor_image = andor_image
#    rw.showImage(andor_image.im)
#    zaic.listen_for_new_image()
#zaic.new_andor_image_received.connect(new_andor_image_received)
#zaic.listen_for_new_image()
#scope.camera.live_mode_enabled = True


import codecs
from ism_blob import ISMBlob
import pickle
import platform
from PyQt5 import Qt
import sys
import threading
import zmq
from .. import scope_configuration as config
from .andor_image import AndorImage

class ZMQAndorImageClient(Qt.QObject):
    new_andor_image_received = Qt.pyqtSignal(object)
    _listen_for_new_image = Qt.pyqtSignal()

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self._worker_thread = Qt.QThread(self)
        self._worker = ZMQAndorImageClient_worker(context)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker.new_andor_image_received.connect(self.new_andor_image_received, Qt.Qt.QueuedConnection)
        self._listen_for_new_image.connect(self._worker._listen_for_new_image, Qt.Qt.QueuedConnection)
        self._worker_thread.start()

    def __del__(self):
        print('~~~~~~~~~~~~~~ZMQAndorImageClient')

    def stop(self):
        self._worker.request_worker_exit()

    def listen_for_new_image(self):
        self._listen_for_new_image.emit()

class ZMQAndorImageClient_worker(Qt.QObject):
    new_andor_image_received = Qt.pyqtSignal(object)

    def __init__(self, context):
        super().__init__()
        self._context = context
        self._req = self._context.socket(zmq.REQ)
        self._req.connect(config.Camera.IMAGE_SERVER_PORT)
        self._sub = self._context.socket(zmq.SUB)
        self._sub.set_hwm(1)
        self._sub.connect(config.Camera.IMAGE_SERVER_NOTIFICATION_PORT)
        self._sub.setsockopt(zmq.SUBSCRIBE, b'')
        self._exit_requested = threading.Event()

    def __del__(self):
        print('~~~~~~~~~~~~~~~ZMQAndorImageClient_worker')

    def request_worker_exit(self):
        self._exit_requested.set()

    def _listen_for_new_image(self):
        while True:
#           print('_listen_for_new_image')
            if self._exit_requested.is_set():
                break
            if self._sub.poll(1000):
                s = self._sub.recv_string(zmq.NOBLOCK)
#               print(s)
                if s == 'new image':
                    self._req.send_json({'req' : 'get newest', 'node' : platform.node()})
#                   print('sent get newest req')
                    image_msg = self._req.recv_json()
#                   print('received get newest req rep')
                    rep = image_msg.pop('rep')
#                   print(rep)
                    if rep == 'ismb image':
#                       print('ismb image')
                        andor_image = AndorImage.reconstruct(**image_msg)
                        self._req.send_json({'req' : 'got', 'ismb_name' : andor_image.ismb.name})
#                       print('sent got req')
                        self._req.recv_json()
#                       print('received got req rep')
                        self.new_andor_image_received.emit(andor_image)
#                       print('emitted')
                    elif rep == 'pickled image':
#                       print('pickled image')
                        andor_image = AndorImage()
                        andor_image.im = pickle.loads(codecs.decode(image_msg['pickled image'].encode('ascii'), 'base64'))
                        self.new_andor_image_received.emit(andor_image)
                    else:
                        sys.stderr.write('Received bad reply to get newest request: {}'.format(str(image_msg)[:128]))
                break
