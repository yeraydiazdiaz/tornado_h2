"""
HTTP2Connection using H2.

"""

import logging

from tornado.http1connection import (
    HTTP1ServerConnection, _ExceptionLoggingContext)
from tornado import gen
from tornado import httputil
from tornado import iostream
from tornado import stack_context
from tornado.log import app_log

from h2.config import H2Configuration
from h2.connection import H2Connection
import h2.settings
import h2.events

log = logging.getLogger('tornado.application')


H2_PREFIXED_HEADERS = ("status", "method", "path", "scheme", "authority")


def prefixed_header(header):
    lo_header = header.lower()
    return ":" + lo_header if lo_header in H2_PREFIXED_HEADERS else lo_header


class HTTP2Connection(object):

    def __init__(self, stream):
        self.stream = stream
        self._write_buffer = b''
        config = H2Configuration(client_side=False, header_encoding='utf-8')
        self.conn = H2Connection(config)
        self._flow_control_future = None

    @gen.coroutine
    def initiate_connection(self):
        log.debug("Initiate connection")
        self.conn.initiate_connection()
        yield self.stream.write(self.conn.data_to_send())

    @gen.coroutine
    def request_received(self, event, delegate, data):
        self.event = event
        self.stream_id = event.stream_id
        log.debug("_request_received: {}".format(self.stream_id))
        if event.headers:
            with _ExceptionLoggingContext(app_log):
                hd = {k: v for k, v in event.headers}
                start_line = httputil.RequestStartLine(
                    method=hd[':method'], path=hd[':path'],
                    version='HTTP/2.0')
                header_future = delegate.headers_received(
                    start_line,
                    httputil.HTTPHeaders(hd)
                )
                if header_future is not None:
                    yield header_future

        delegate.data_received(data)
        with _ExceptionLoggingContext(app_log):
            delegate.finish()
        raise gen.Return(True)

    def write_headers(self, start_line, headers, chunk=None, callback=None):
        """Tornado's implementation might include a chunk of data, which may
        be the full response if small enough.

        TODO: handle the callback.

        """
        log.debug("Write headers: {}".format(headers))

        self.start_line = start_line

        self.headers = headers
        if self.headers.get_list('Content-Length'):
            self.bytes_to_send = int(
                self.headers.get_list('Content-Length')[0])
            log.debug('{}'.format(self.bytes_to_send))

        self._send_headers()

        if chunk:
            if len(chunk) > self.conn.remote_settings.max_frame_size:
                # TODO: the chunk size is derived from the delegates self.write
                # since we're returning a future we cannot break the chunk and
                # use write to send them, ideally we'd negotiate a bigger frame
                # size but I'm unsure of the mechanism and if it would even
                # could negociate at this point or we need to move it elsewhere
                log.warning('Chunk size exceeds max_frame_size')
                self._pending_chunk = chunk[
                    self.conn.remote_settings.max_frame_size:]
                chunk = chunk[
                    :self.conn.remote_settings.max_frame_size]

            log.debug("Write_headers: send {} bytes with end_stream={}".format(
                len(chunk), self.bytes_to_send - len(chunk) <= 0))
            self._send_data(chunk, self.bytes_to_send - len(chunk) <= 0)
            self.bytes_to_send -= len(chunk)

        return self.stream.write(self.conn.data_to_send())

    def write(self, chunk, callback=None):
        """Handles additional chunks being flushed.

        For HTTP2 we simply append it to the chunk to be sent in the stream

        """
        if not chunk:
            log.debug('Write: No chunk')
            return

        log.debug('Write {}'.format(len(chunk)))
        # if no more data can be sent on this stream hold on for the next window
        while not self.conn.remote_flow_control_window(self.stream_id):
            log.debug('Waiting for flow control')
            return self.wait_for_flow_control()

        # TODO: use the code below to cut off remaining chunk depending
        # on the remote_flow_control_window
        # chunk_size = min(
        #     self.conn.remote_flow_control_window(self.stream_id), 8192
        # )
        log.debug('Adding chunk {} - {} = {}'.format(
            self.bytes_to_send, len(chunk), self.bytes_to_send - len(chunk)))
        log.debug("write: send_data with end_stream={}".format(
            self.bytes_to_send - len(chunk) <= 0))
        self._send_data(chunk, self.bytes_to_send - len(chunk) <= 0)
        self.bytes_to_send -= len(chunk)
        # stream.write returns a Future
        return self.stream.write(self.conn.data_to_send())

    def wait_for_flow_control(self):
        """Creates a future which will be resolved on the next WindowUpdated.

        """
        log.debug('Waiting for flow control')
        # TODO: expand to different stream_ids
        self._flow_control_future = gen.Future()
        return self._flow_control_future

    def window_updated(self, event):
        """Handler for the windowUpdated event. Send all data.

        """
        log.debug('WindowUpdated')
        # TODO: use for different stream_ids
        if self._flow_control_future is not None:
            log.debug('Resolving flow control future')
            # TODO: does this resolve the Future?
            self._flow_control_future.set_result(event.delta)
            self._flow_control_future = None

    def request_ended(self, event):
        """Handler for StreamEnded.

        Seems H2 wants the data to be sent at this point, but it competes with
        Tornado's finish mechanism.

        """
        log.debug('Got StreamEnded')

    def receive_data(self, data):
        return self.conn.receive_data(data)

    def data_to_send(self):
        return self.conn.data_to_send()

    def close_connection(self):
        self.conn.close_connection()

    def _get_response_headers(self):
        response_headers = [
            (prefixed_header(header), value)
            for header, value in self.headers.items()
        ]
        response_headers.append((":status", str(self.start_line.code)))
        return sorted(response_headers)

    def _send_headers(self):
        self.conn.send_headers(
            stream_id=self.stream_id,
            headers=self._get_response_headers()
        )
        log.debug('Headers sent!!')

    def _send_data(self, chunk, end_stream=False):
        self.conn.send_data(
            stream_id=self.stream_id,
            data=chunk,
            end_stream=end_stream
        )
        log.debug('Data sent!!')

    def set_close_callback(self, callback):
        """Required by RequestHandler init for backwards compatibility.

        """
        self._close_callback = stack_context.wrap(callback)

    def remote_settings_changed(self, event):
        """Handle changes in the remote settings

        TODO: use SettingCodes.MAX_FRAME_SIZE to drive StaticFileHandler's
        get_content and possibly other settings for large data chunks in write.
        """
        log.debug('Remote settings changed handler')
        log.info(event)

    def settings_acknowledged(self, event):
        """Handle acknowledgement of settings.

        """
        log.debug('Settings acknowledged')
        log.info(event)

    @gen.coroutine
    def finish(self):
        """Hook into Tornado's handlers for finishing a request.

        """
        # TODO: this is less than elegant but covers the case where the
        # delegate tries to send a chunk larger than the current max_frame_size
        # in `write_headers` we cannot handle it there since we need to return
        # a Future so we handle it here.
        if hasattr(self, '_pending_chunk'):
            log.warning('Pending data in finish')
            while self.bytes_to_send > 0:
                chunk = self._pending_chunk[
                    :self.conn.remote_settings.max_frame_size]
                self._pending_chunk = self._pending_chunk[
                    self.conn.remote_settings.max_frame_size:]
                self.bytes_to_send -= len(chunk)
                self._send_data(chunk, self.bytes_to_send <= 0)
                yield self.stream.write(self.conn.data_to_send())

        raise gen.Return()


class HTTP2ServerConnection(HTTP1ServerConnection):
    """An HTTP/2.x server connection, bridging to H2Connection.

    """

    @gen.coroutine
    def _server_request_loop(self, delegate):
        log.debug(
            "HTTP2ServerConnection loop with delegate {}".format(delegate))
        conn = HTTP2Connection(self.stream)
        yield conn.initiate_connection()
        request_delegate = delegate.start_request(self, conn)

        while True:
            try:
                data = yield self.stream.read_bytes(65535, partial=True)
            except iostream.StreamClosedError:
                conn.close_connection()
                break

            if not data:
                log.debug('No data read from TCP stream')
                continue

            events = conn.receive_data(data)
            log.debug('Read events')
            for event in events:
                log.debug("EVENT: {}".format(event))
                if isinstance(event, h2.events.RequestReceived):
                    yield conn.request_received(
                        event, request_delegate, data)
                # elif isinstance(event, h2.events.DataReceived):
                #     conn.reset_stream(event.stream_id)
                elif isinstance(event, h2.events.StreamEnded):
                    # TODO: we need to properly handle a StreamEnded
                    conn.request_ended(event)
                elif isinstance(event, h2.events.RemoteSettingsChanged):
                    conn.remote_settings_changed(event)
                elif isinstance(event, h2.events.SettingsAcknowledged):
                    conn.settings_acknowledged(event)
                elif isinstance(event, h2.events.WindowUpdated):
                    conn.window_updated(event)
                elif isinstance(event, h2.events.ConnectionTerminated):
                    conn.close_connection()

            buffer = conn.data_to_send()
            if buffer:
                log.debug('Writing to TCP stream: {}'.format(buffer))
                yield self.stream.write(buffer)
