"""
HTTP2Server to use HTTP2ServerConnection.

"""

from tornado import gen
from tornado import httputil
from tornado.tcpserver import TCPServer
from tornado.util import Configurable
from tornado.http1connection import HTTP1ConnectionParameters
from tornado.httpserver import (
    _HTTPRequestContext, _CallableAdapter, _ProxyAdapter)

from tornado_h2.http2serverconnection import HTTP2ServerConnection


class HTTP2Server(
        TCPServer, Configurable, httputil.HTTPServerConnectionDelegate):

    def __init__(self, *args, **kwargs):
        pass

    def initialize(self, request_callback, no_keep_alive=False, io_loop=None,
                   xheaders=False, ssl_options=None, protocol=None,
                   decompress_request=False,
                   chunk_size=None, max_header_size=None,
                   idle_connection_timeout=None, body_timeout=None,
                   max_body_size=None, max_buffer_size=None):
        self.request_callback = request_callback
        self.no_keep_alive = no_keep_alive
        self.xheaders = xheaders
        self.protocol = protocol
        self.conn_params = HTTP1ConnectionParameters(
            decompress=decompress_request,
            chunk_size=chunk_size,
            max_header_size=max_header_size,
            header_timeout=idle_connection_timeout or 3600,
            max_body_size=max_body_size,
            body_timeout=body_timeout)
        TCPServer.__init__(self, io_loop=io_loop, ssl_options=ssl_options,
                           max_buffer_size=max_buffer_size,
                           read_chunk_size=chunk_size)
        self._connections = set()

    @classmethod
    def configurable_base(cls):
        return HTTP2Server

    @classmethod
    def configurable_default(cls):
        return HTTP2Server

    @gen.coroutine
    def close_all_connections(self):
        while self._connections:
            # Peek at an arbitrary element of the set
            conn = next(iter(self._connections))
            yield conn.close()

    def handle_stream(self, stream, address):
        context = _HTTPRequestContext(stream, address, self.protocol)
        conn = HTTP2ServerConnection(stream, self.conn_params, context)
        self._connections.add(conn)
        conn.start_serving(self)

    def start_request(self, server_conn, request_conn):
        if isinstance(
                self.request_callback, httputil.HTTPServerConnectionDelegate):
            delegate = self.request_callback.start_request(
                server_conn, request_conn)
        else:
            delegate = _CallableAdapter(self.request_callback, request_conn)

        if self.xheaders:
            delegate = _ProxyAdapter(delegate, request_conn)

        return delegate

    def on_close(self, server_conn):
        self._connections.remove(server_conn)
