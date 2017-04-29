"""
Extensions to the web.py module for use in HTTP2

"""
import logging

from tornado.web import StaticFileHandler

log = logging.getLogger(__name__)


class HTTP2StaticFileHandler(StaticFileHandler):
    """Subclass of the StaticFileHandler with flexible chunk size support.

    Requires specifically setting it as static file handler in the Router
    of Application object.

    """

    def should_return_304(self):
        """Skip cache.

        """
        return False

    @classmethod
    def get_content(cls, abspath, start=None, end=None, chunk_size=16 * 1024):
        """Reimplementation with a slight change to allow for different chunk size.

        Default was 64 * 1024

        """
        with open(abspath, "rb") as file:
            if start is not None:
                file.seek(start)
            if end is not None:
                remaining = end - (start or 0)
            else:
                remaining = None
            while True:
                if remaining is not None and remaining < chunk_size:
                    chunk_size = remaining
                chunk = file.read(chunk_size)
                if chunk:
                    if remaining is not None:
                        remaining -= len(chunk)
                    log.debug('Yielding chunk of size {}'.format(len(chunk)))
                    yield chunk
                else:
                    if remaining is not None:
                        assert remaining == 0
                    return
