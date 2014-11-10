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

from .andor_image import AndorImage
import ctypes
from ism_blob import ISMBlob
from . import lowlevel
import numpy
import os
import platform
from .. import scope_configuration as config
import sys
import threading
import weakref
import zmq


_c_uint8_p = ctypes.POINTER(ctypes.c_uint8)
_c_uint32_p = ctypes.POINTER(ctypes.c_uint32)
_c_uint64_p = ctypes.POINTER(ctypes.c_uint64)

class AndorImageServer:
    def __init__(self, camera):
        self.camera = weakref.proxy(camera)

    @property
    def in_live_mode(self):
        return self._get_in_live_mode()

    @in_live_mode.setter
    def in_live_mode(self, in_live_mode):
        self._set_in_live_mode(in_live_mode)

    def _get_in_live_mode(self):
        raise NotImplementedError()

    def _set_in_live_mode(self, in_live_mode):
        raise NotImplementedError()

class LocalAndorImageServer(AndorImageServer):
    def __init__(self, camera):
        super().__init__(camera)

class ZMQAndorImageServer(AndorImageServer):
    def __init__(self, camera, context):
        self.context = context
        self._rep_socket = self.context.socket(zmq.REP)
        self._rep_socket.bind(config.Camera.IMAGE_SERVER_PORT)
        self._pub_socket = self.context.socket(zmq.PUB)
        self._pub_socket.set_hwm(1)
        self._pub_socket.bind(config.Camera.IMAGE_SERVER_NOTIFICATION_PORT)
        self._pub_lock = threading.Lock()
        super().__init__(camera)
        self._msg_handlers = {
            'stop' : self._on_stop,
            'get newest' : self._on_get_newest,
            'got' : self._on_got
        }
        self._newest = None
        self._newest_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._in_live_mode = False
        self._in_live_mode_cv = threading.Condition()
        self._stop_requested = threading.Event()
        self._im_sequence_number = -1
        self._on_wire = {}
        self._req_handler_thread = threading.Thread(target=ZMQAndorImageServer._req_handler_threadproc,
                                                    args=(weakref.proxy(self),),
                                                    name='ZMQAndorImageServer req handler',
                                                    daemon=False)
        self._live_acquisition_thread = threading.Thread(target=ZMQAndorImageServer._live_acquisition_threadproc,
                                                         args=(weakref.proxy(self),),
                                                         name='ZMQAndorImageServer live acquisition',
                                                         daemon=False)
        self._live_acquisition_thread.start()
        self._req_handler_thread.start()

#   def __del__(self):
#       print('~~~~~~~~~~~~~~~~~~~~~~~~~~~ZMQAndorImageServer.__del__~~~~~~~~~~~~~~~~~~~~~~~~~~~')

    def stop(self):
        self._stop_requested.set()
        # Prod live thread if it's asleep (waiting forever for a request to enter live mode)
        with self._in_live_mode_cv:
            if not self._in_live_mode:
                self._in_live_mode_cv.notify()

    def _get_in_live_mode(self):
        with self._in_live_mode_cv:
            return self._in_live_mode

    def _set_in_live_mode(self, in_live_mode):
        with self._in_live_mode_cv:
            if in_live_mode != self._in_live_mode:
                self._in_live_mode = in_live_mode
                if self._in_live_mode:
                    self.camera.trigger_mode.set_value('Software')
                    self.camera.cycle_mode.set_value('Continuous')
                    lowlevel.Flush()
                    lowlevel.Command('AcquisitionStart')
                    self._in_live_mode_cv.notify()
                else:
                    lowlevel.Command('AcquisitionStop')
                    lowlevel.Flush()

    def _live_acquisition_threadproc(self):
        while not self._stop_requested.is_set():
            with self._in_live_mode_cv:
                if not self._in_live_mode:
#                   print('********waiting')
                    self._in_live_mode_cv.wait()
#                   print('********done waiting')
                    if not self._in_live_mode:
                        # Either the user toggled live mode faster than we could respond, or a stop
                        # request has been received.
                        continue
            try:
                # We are in live mode.  Acquire an image.
                im_bytecount = self.camera.get_image_byte_count()
                im_encoding = self.camera.pixel_encoding.get_value()
                im_width = self.camera.get_aoi_width()
                im_height = self.camera.get_aoi_height()
                im_row_stride = self.camera.get_aoi_stride()
                im_has_timestamp = self.camera.get_metadata_enabled() and self.camera.get_include_timestamp_in_metadata()
                im_exposure_time = self.camera.get_exposure_time()
                im_timestamp = None
                self._im_sequence_number += 1
#               print('acquiring {}'.format(self._im_sequence_number))
                im_ismb = ISMBlob.new('ZMQAndorImageServer_{}_{:010}.ismb'.format(os.getpid(), self._im_sequence_number),
                                      (im_height, im_width),
                                      numpy.uint16)
                im = im_ismb.asarray()
                imr = numpy.empty((im_bytecount), numpy.uint8)
                c_imr = imr.ctypes.data_as(_c_uint8_p)
                lowlevel.QueueBuffer(c_imr, im_bytecount)
                lowlevel.Command('SoftwareTrigger')
                if ctypes.cast(lowlevel.WaitBuffer(max(im_exposure_time * 1000 + 250, 500))[0], ctypes.c_void_p).value != imr.ctypes.data:
                    raise lowlevel.AndorError('WaitBuffer filled a different buffer than expected.')
                # Mono12Packed images require unpacking, which ConvertBuffer handles competently.
                # Mono16 typically images contain padding at the end of each row (stride) which
                # must be removed via copy operation in order make an array that is contiguous in
                # memory.  This could be accomplished via im[:,:] = imr[:2160,:2560], which took
                # about 1.63ms when tested.  Using ConvertBuffer to achieve the same required 1.64ms,
                # which is within benchmarking margin of error, so ConvertBuffer is used in all cases.
                lowlevel.ConvertBuffer(c_imr,
                                       ctypes.cast(im.ctypes.data, _c_uint8_p),
                                       im_width,
                                       im_height,
                                       im_row_stride,
                                       im_encoding,
                                       'Mono16')
                if im_has_timestamp:
                    p = imr.ctypes.data + im_bytecount
                    while True:
                        p -= 8
                        cid, md_block_len = ctypes.cast(p, _c_uint32_p)[0:1]
                        if cid == 1:
                            p -= 8
                            im_timestamp = ctypes.cast(p, _c_uint64_p)[0]
                            print('im_timestamp')
                            break
                        else:
                            # -4: md_block_len (metadata block length) does not include the length
                            # field itself
                            p -= md_block_len - 4
                            if p < imr.ctypes.data + 8:
                                raise lowlevel.AndorError('Failed to find timestamp in image metadata.')
                aim = AndorImage(im, im_timestamp, im_exposure_time, self._im_sequence_number)
                self._notify_of_new_image(aim)
#               print('notified {}'.format(self._im_sequence_number))
            except lowlevel.AndorError as e:
                # TODO: inform clients of the details of the error.  Currently, the client knows
                # that live mode exited spontaneously but not why.
                sys.stderr.write('Exiting live mode due to {}\n'.format(str(e)))
                sys.stderr.flush()
                self.camera.set_live_mode_enabled(False)

    def _req_handler_threadproc(self):
        while not self._stop_requested.is_set():
            if self._rep_socket.poll(500):
                msg = self._rep_socket.recv_json(zmq.NOBLOCK)
                req = msg['req']
                handler = self._msg_handlers.get(req, self._unknown_req)
                handler(msg)

    def _notify_of_new_image(self, andor_image):
        with self._newest_lock:
            self._newest = andor_image
        with self._pub_lock:
            self._pub_socket.send_string('new image')

    def _unknown_req(self, msg):
        sys.stderr.write('Warning: Received unknown request string "{}".'.format(msg['req']))
        sys.stderr.flush()
        rmsg = {
            'rep' : 'ERROR',
            'error' : 'Unknown request string',
            'req' : msg['req']
        }
        self._rep_socket.send_json(rmsg)

    def _on_stop(self, _):
        with self._pub_lock:
            self._pub_socket.send_string('stopping')
        self._rep_socket.send_json({'rep' : 'stopping'})
        self.stop()

    def _on_get_newest(self, msg):
        with self._newest_lock:
            newest = self._newest
        if newest is None:
            self._rep_socket.send_json({'rep' : 'none available'})
        else:
            ismb_name = newest.im.base.base.name
#           print(ismb_name)
            if msg['node'] != '' and msg['node'] == platform.node():
                rmsg = {
                    'rep' : 'ismb image',
                    'ismb_name' : ismb_name,
                    'sequence_number' : newest.sequence_number,
                    'exposure_time' : newest.exposure_time,
                    'timestamp' : newest.timestamp
                    }
                self._rep_socket.send_json(rmsg)
                if ismb_name in self._on_wire:
                    self._on_wire[ismb_name][1] += 1
                else:
                    self._on_wire[ismb_name] = [newest, 1]
            else:
                rmsg = {
                    'rep' : 'raw image',
                    'sequence_number' : newest.sequence_number,
                    'exposure_time' : newest.exposure_time,
                    'timestamp' : newest.timestamp,
                    'shape' : newest.im.shape
                }
                self._rep_socket.send_json(rmsg, zmq.SNDMORE)
                # ZMQ keeps a reference to newest.im however long it requires
                self._rep_socket.send(newest.im, copy=False)

    def _on_got(self, msg):
        ismb_name = msg['ismb_name']
        if ismb_name in self._on_wire:
            onwire = self._on_wire[ismb_name]
            onwire[1] -= 1
            if onwire[1] == 0:
                del self._on_wire[ismb_name]
            self._rep_socket.send_json({'rep' : 'ok'})
        else:
            sys.stderr.write('Warning: ismb_name "{}" in got request absent from _on_wire dict.'.format(ismb_name))
            sys.stderr.flush()
            self._rep_socket.send_json({'rep' : 'ERROR', 'error' : 'Specified AndorImage is not in _on_wire dict.'})
