# Tornado H2

An HTTP/2 server integrated with [Tornado](https://tornadoweb.org) using [hyper-h2](https://python-hyper.org/h2/en/stable/).

Check out [PythonTiles](http://bit.ly/2qed5YY), a quick example inspired by [GopherTiles](https://http2.golang.org/gophertiles)

**Please note**: This in no way fully compliant, is missing many features (and tests) and it's very likely there are better ways to implement it, the intention was to have a server that plugs into the Tornado web framework allowing `RequestHandler`s to return content correctly.

## Setup and run

- Clone this repo
- Create a virtual env
- `python setup.py develop`
- `pip install -r examples/requirements.txt`
- `python examples/tornado_h2_server_example.py`
- Visit the URL in the output in the browser, if https is specified make sure to accept the certificate
