System for controlling ZP lab microscopes from python code. The system has a few
moving parts (literally and figuratively), so here's an introduction. Currently
Leica DM6000 and DMi8 are supported, with Andor Zyla cameras.

High-Level Architecture
-----------------------
(1) The microscope-driving code runs as a server. Users and GUIs connect to
the "scope daemon" and send it commands, over a simple RPC protocol. (JSON
transmitted over ZeroMQ sockets.) These connections can be either local or over
the network.

(2) In addition to the command-driven RPC connections, the server also publishes
updates about changes to the state of the microscope that clients can subscribe
to. This is useful for both GUIs and for getting updates about things like when
a new image is available in live-viewing mode.

(3) The server transfers images to local clients via named shared memory areas,
which enables fast, zero-copy transfers of large quantities of image data.
Remote clients instead get data serialized over the RPC connection.

(4) On the server-side, the microscope itself is represented as a "Scope"
object with sub-objects referring to various hardware components attached,
including the camera, temperature controller, etc.

(5) The Leica scope itself has a fairly rich/complex serial API that involves
sending and receiving commands, possibly in asynchronous fashion. So there is a
set of message-manager classes that mind the serial port in a background thread
and take care of sending messages to the serial port and calling the
appropriate callbacks when messages are received. Any microscope components can
be set to "synchronous" mode where functions don't return until the microscope
is done executing them, or "async_" mode where all functions return immediately,
except wait() which will block until all previous outstanding functions are
done executing.

(6) The Andor camera is also rather complex, and like the Leica scope, is
effectively a state machine. Lowlevel wrappers for the Andor C API are auto-
generated, and then prettified into a Camera object that encapsulates most
of the complexity. Advanced users will likely need to read both the camera's
hardware manual and SDK documentation.

(7) Several components are integrated by a custom microcontroller that sends
and receives TTL pulses and PWM analog signals. This microcontroller, IOTool,
is used to sequence camera acquisitions in synch with light pulses from the
transmitted lamp and the Spectra X fluorescence excitation source.

Specific Details
----------------

*RPC Protocol*
The RPC client and server code is in `simple_rpc/rpc_[client|server].py`

Methods of the microscope controller object (and its attributes) are exposed to
clients via a simple RPC protocol that consists of JSON messages sent over
ZeroMQ request/reply sockets. Why? Several reasons: first, users can connect
locally OR remotely, and from Python or any other language they choose if it
supports ZeroMQ. Next, this allows any microscope GUIs to be totally decoupled
from the "scope daemon" that actually drives the hardware. Finally, multiple
clients can connect at once, which seems like a bad idea, but allows one to
remotely check up on the microscope state during long data acquisition runs.

In addition to the basic RPC server, an out-of-band "Interrupt Server" is also
run over a separate socket, which allows "KeyboardInterrupt" signals to be sent
to break out of any RPC command.

The basic RPC protocol is that the client sends a JSON encoding of the command
name, its args, and kwargs. The server then looks up the command name, calls
the command, and replies in a multi-part ZeroMQ message. The first part
specifies if the reply contains error data (which is JSON-serialized, and
intended to be raised as an exception on the client side), JSON reply data, or
binary reply data. The server can also provide detailed descriptions of all the
commands in its namespace, allowing the client to build up a rich set of proxy
functions to be called.

*Property Protocol*
The property client and server code is in 
`simple_rpc/property_[client|server].py`

In addition to an imperative RPC architecture, there is an asynchronous
"property server" that allows clients to be notified of any changes to the state
of the microscope or its components. This is mostly useful for GUI programs, but
is also used when the camera's "live mode" is on to notify clients when new
images are available.

This is a fairly straightforward use of ZeroMQ publish/subscribe sockets, with
some cleverness on the client side to allow callbacks to be registered for
updates to specific properties, or to all properties with a common prefix. Scope
properties are named e.g. `scope.stage.x`, so common prefixes are very useful.

*Interprocess Shared Memory*
This uses the "ISM_Buffer" library that we wrote:
https://github.com/zplab/SharedMemoryBuffer
and tools in `transfer_ism_buffer.py`.

ISM_Buffers are named, shared-memory regions that can be opened by different
processes and allow for zero-copy sharing of data between processes. (Moreover,
ISM_Buffers can serve as the backing memory for numpy arrays.) To allow this to
be more seamless, ISM_Buffers maintain a shared reference count, so when the
last python reference to a given ISM_Buffer is deleted, it will tear down the
whole ISM_Buffer too, preventing memory leaks.

These buffers must be handed from the server to the client carefully to ensure
that the server doesn't acidentally tear down the ISM_Buffer before the client
receives it and increments its reference count. This is accomplished as follows:

First, on the server, a named `ISM_Buffer` is created (in
`transfer_ism_buffer.py`), and a numpy array that is a view onto that shared
memory is created. Any function that returns an "image" to the client must
first register the `ISM_Buffer` by name (via
`transfer_ism_buffer.register_array_for_transfer()`) which causes the
server to keep a reference to the ISM_Buffer-backed array around. Then the
ISM_Buffer's name is returned to the client, which the client can use to create
its own ISM_Buffer view onto that memory. Once this is accomplished, the client
calls `transfer_ism_buffer._server_release_array()` to tell the server that it
need no longer keep it's own reference.

This is all taken care of by `transfer_ism_buffer.client_get_data_getter()`,
which returns a function called `get_data()` that, given a ISM_Buffer name,
performs all of the above steps. The scope client even monkeypatches things so
that all known calls that return an ISM_Buffer name get wrapped with this
`get_data()` function, so that things work transparently.

*Network Image Streaming* The above is all well and good if the client is local
on that machine and can access the shared memory. If the client is remote, then
it must ask the server to pack the named ISM_Buffer's memory into binary data
and send that over RPC. This is also transparently handled by
`transfer_ism_buffer.client_get_data_getter()`, which will detect if the client
and server are not on the same machine, and return a `get_data()` function that
causes network data transfer to occur.

*Message-Based Devices (Leica Scope)*
The relevant code is `messaging/message_[device|manager].py`

For the Leica microscope, a `MessageManager` controls access to a serial port in
a background thread. Messages are queued up to be sent over, with callback
functions to be called when a reply to that given message is received. (Replies
and callbacks are matched up via a "key" generated based on the reply contents.)

Each class that represents a part of the microscope is a subclass of
`message_device.AsyncDevice`. This base class interacts with a `MessageManager`
to send and receive messages either in an async_ mode (where seveal messages can
be sent before calling `wait()` to block until all have been replied to) or in
synchronous mode where sending a message blocks until the reply for that
message is received.
