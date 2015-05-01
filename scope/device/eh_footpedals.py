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

import re
import threading
import time

from ..config import scope_configuration
from ..util import logging
from ..util import smart_serial
from ..util import property_device

class EhFootPedals(property_device.PropertyDevice):
    def __init__(self, property_server=None, property_prefix=''):
        super().__init__(property_server, property_prefix)
        config = scope_configuration.get_config()
        self._serial_port = smart_serial.Serial(
            config.EhFootPedals.SERIAL_PORT, baudrate=config.EhFootPedals.SERIAL_BAUD)
        self._init_serial_connection()

#       self._serial_port.write('get numberOfPedals\n'.encode('ascii'))
#       try:
#           self._serial_port.read_until('\r\n')

    def _init_serial_connection(self):
        # Clear microcontroller and host input buffers
        self._serial_port._timeout = 0.5
        try:
            # NB: The production for the Python for statement is:
            # for_stmt ::=  "for" target_list "in" expression_list ":" suite
            #               ["else" ":" suite]
            # The else clause executes if the for loop was not terminated via break.
            for _ in range(2):
                self._send_command('')
                try:
                    # In _get_response, it is safe to assume that a multiline error begins with /*, allowing
                    # the entire error to be retrieved by read_until('/*\r\n') in the case where the response
                    # line received did not end with /*CRLF.  Here, we may potentially receive only the later
                    # portion of a multiline error, and so we must attempt to read until /*CRLF
                    try:
                        self._serial_port.read_until('/*\r\n')
                    except smartserial.SerialTimeout:
                        try:
                            self._serial_port.read_until('/\r\n')
                        except smartserial.SerialTimeout:
                            pass
                        else:
                            break
            else:
                raise smart_serial.SerialException('Could not read data from EhFootPedals device -- is it attached to this computer?')
        finally:
            self._serial_port._timeout = None

    def _send_command(self, c):
        self._serial_port.write((c + '\n').encode('ascii'))

    def _get_response(self):
        r = 
