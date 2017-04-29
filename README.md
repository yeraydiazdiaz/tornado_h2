# Tornado H2

An HTTP/2 server integrated with [Tornado](https://tornadoweb.org) using [hyper-h2](https://python-hyper.org/h2/en/stable/).

Check out [PythonTiles](http://bit.ly/2qed5YY), a [quick example](https://github.com/yeraydiazdiaz/tornado_h2/blob/master/examples/tornado_h2_python_tiles.py) inspired by [GopherTiles](https://http2.golang.org/gophertiles).

It implements an `HTTP2Server` which accepts standard Tornado `Application` objects and seamlessly returns responses from `web.RequestHandler` objects through HTTP/2.

**Please note**: This is not fully compliant and it's missing many features (and tests).

## Setup and run

- Clone this repo
- Create a virtual env
- `python setup.py develop`
- `pip install -r examples/requirements.txt`
- `python examples/tornado_h2_server_example.py`
- Visit the URL in the output in the browser, if https is specified make sure to accept the certificate
