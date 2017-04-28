"""
Tornado-H2 Python tiles application, an example HTTP2 push using Tornado-H2.

Inspired by https://http2.golang.org/gophertiles.

"""

import os
import ssl
import logging
from io import BytesIO
from collections import namedtuple

from PIL import Image
import tornado.gen
import tornado.ioloop
import tornado.iostream
import tornado.tcpserver
import tornado.web
from tornado.options import options

import log
import tornado_h2.http2server as th2
from tornado_h2 import http2_web

logger = logging.getLogger('tornado.application')

options.define(
    'address', default='0.0.0.0',
    help='IP address to attach the server to', type=str)
options.define(
    'port', default=os.environ.get('PORT', 8888),
    help='Port number to run the server on', type=int)
options.define(
    'https', default=True,
    help='Start application with HTTPS?', type=bool)
options.define(
    'debug', default=True,
    help='Start application in debug mode?', type=bool)

options.define(
    'image_name', default='burmese_python.jpg',
    help='File name of the image in the examples/static directory')
options.define(
    'max_tiles', default=8,
    help="The number of tiles to divide the image, defaults to 8 (8x8)")


Point = namedtuple('Point', ('x', 'y'))


class TileOutOfBoundsError(Exception):
    pass


def create_ssl_context(certfile, keyfile):
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.options |= (
        ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1 | ssl.OP_NO_COMPRESSION
    )
    ssl_context.set_ciphers('ECDHE+AESGCM')
    ssl_context.load_cert_chain(certfile=certfile, keyfile=keyfile)
    ssl_context.set_alpn_protocols(['h2'])
    return ssl_context


class TileHandler(tornado.web.RequestHandler):
    """Handler to create tiles for an image `img` in the closure.

    GET `tile/N` returns a localised crop of the image as defined by
    `max_tiles`.

    """

    def compute_etag(self):
        return None

    def get_tile(self, tile_number):
        """Returns a crop of `img` based on a sequence number `tile_number`.

        :param int tile_number: Number of the tile between 0 and `max_tiles`^2.
        :raises TileOutOfBoundsError: When `tile_number` exceeds `max_tiles`^2
        :rtype PIL.Image:

        """
        tile_number = int(tile_number)
        max_tiles = options.max_tiles
        if tile_number > max_tiles * max_tiles:
            raise TileOutOfBoundsError('Requested an out of bounds tile')

        tile_size = Point(img.size[0] // max_tiles, img.size[1] // max_tiles)
        tile_coords = Point(tile_number % max_tiles, tile_number // max_tiles)
        crop_box = (
            tile_coords.x * tile_size.x,
            tile_coords.y * tile_size.y,
            tile_coords.x * tile_size.x + tile_size.x,
            tile_coords.y * tile_size.y + tile_size.y,
        )
        return img.crop(crop_box)

    @tornado.gen.coroutine
    def get(self, tile_number):
        """Handles GET requests for a tile number.

        :param int tile_number: Number of the tile between 0 and `max_tiles`^2.
        :raises HTTPError: 404 if tile exceeds `max_tiles`^2.
        """
        # yield tornado.gen.sleep(5)
        try:
            tile = self.get_tile(tile_number)
        except TileOutOfBoundsError:
            raise tornado.web.HTTPError(404)

        buf = BytesIO(tile.tobytes())
        tile.save(buf, 'JPEG')

        content = buf.getvalue()
        self.set_header('Content-Type', 'image/jpg')
        self.set_header('Accept-Ranges', 'bytes')
        self.set_header('Content-Length', len(content))
        self.write(content)


class HomePageHandler(tornado.web.RequestHandler):
    """Simple handler for showing a template with a header and the image tiles.

    """

    def get(self):
        self.render('template.html', max_tiles=options.max_tiles)

    def compute_etag(self):
        return None


class TestPageHandler(tornado.web.RequestHandler):

    def get(self):
        # self.write(
        #     '<h1>Hello HTTP/2!!</h1><img src="static/burmese_python.jpg" />')
        self.write('<h1>Hello HTTP/2!!</h1>')

    def compute_etag(self):
        return None


class PythonTilesApplication(tornado.web.Application):
    """Application defining home, static and tile endpoints for Python tiles.

    """

    def __init__(self):
        settings = {
            'debug': options.debug,
        }
        handlers = [
            (r'/', HomePageHandler, {}, 'home'),
            (r'/test/', TestPageHandler, {}, 'test'),
            (r'/tile/(\d+)', TileHandler, {}, 'tile'),
            (r'/static/(.*)', http2_web.HTTP2StaticFileHandler,
                {
                    'path': os.path.join(os.path.dirname(__file__), 'static')
                }, 'static'),
        ]

        super().__init__(handlers, **settings)


if __name__ == '__main__':
    base_path = os.path.dirname(__file__)
    path_to_image = os.path.join(base_path, 'static', 'burmese_python.jpg')
    img = Image.open(path_to_image)
    options.parse_command_line()
    log.setup_logging()

    ssl_paths = [
        os.path.join(base_path, f) for f in ('server.crt', 'server.key')]
    ssl_context = create_ssl_context(*ssl_paths) if options.https else None

    app = PythonTilesApplication()
    server = th2.HTTP2Server(app, ssl_options=ssl_context)
    logger.info('Starting HTTP2 server on http{}://{}:{}'.format(
        's' if options.https else '', options.address, options.port))
    server.bind(options.port, address=options.address)
    server.start()

    io_loop = tornado.ioloop.IOLoop.current()
    io_loop.start()
