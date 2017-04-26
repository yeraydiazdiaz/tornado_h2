"""
Example application for Tornado-H2 server.

Serves responses from RequestHandlers and static files served using
HTTP2StaticFileHandler.

"""

import os
import ssl
import logging

import tornado.gen
import tornado.ioloop
import tornado.iostream
import tornado.tcpserver
import tornado.web
from tornado.options import options

import log
import tornado_h2.http2server as th2
from tornado_h2.http2_web import HTTP2StaticFileHandler

logger = logging.getLogger('tornado.application')

options.define(
    "address", default='0.0.0.0',
    help="IP address to attach the server to", type=str)
options.define(
    "port", default=os.environ.get('PORT', 8888),
    help="Port number to run the server on", type=int)
options.define(
    "https", default=True,
    help="Start application with HTTPS?", type=bool)
options.define(
    "debug", default=True,
    help="Start application in debug mode?", type=bool)


def create_ssl_context(certfile, keyfile):
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.options |= (
        ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1 | ssl.OP_NO_COMPRESSION
    )
    ssl_context.set_ciphers("ECDHE+AESGCM")
    ssl_context.load_cert_chain(certfile=certfile, keyfile=keyfile)
    ssl_context.set_alpn_protocols(["h2"])
    return ssl_context


class MainHandler(tornado.web.RequestHandler):

    def get(self):
        self.write('<h1>Hello HTTP/2!!</h1>')

    def compute_etag(self):
        return None


class HTTP2ExampleApplication(tornado.web.Application):

    def __init__(self):
        settings = {
            'debug': options.debug,
        }
        handlers = [
            (r'/', MainHandler, {}, 'home'),
            # Avoid using Tornado's StaticFileHandler
            (r'/static/(.*)', HTTP2StaticFileHandler,
                {'path': os.path.join(os.path.dirname(__file__), 'static')},
                'static'),
        ]

        super().__init__(handlers, **settings)


if __name__ == '__main__':
    base_path = os.path.dirname(__file__)
    options.parse_command_line()
    log.setup_logging()

    ssl_paths = [
        os.path.join(base_path, f) for f in ('server.crt', 'server.key')]
    ssl_context = create_ssl_context(*ssl_paths) if options.https else None

    app = HTTP2ExampleApplication()
    server = th2.HTTP2Server(app, ssl_options=ssl_context)
    logger.info("Starting HTTP2 server on http{}://{}:{}".format(
        "s" if options.https else "", options.address, options.port))
    server.bind(options.port, address=options.address)
    server.start()

    io_loop = tornado.ioloop.IOLoop.current()
    io_loop.start()
