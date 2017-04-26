try:
    import setuptools
    from setuptools import setup
except ImportError:
    setuptools = None
    from distutils.core import setup

version = '0.0.1'

setup(
    name='tornado_h2',
    version=version,
    packages=['tornado_h2'],
    install_requires=['h2>=3.0.1', 'tornado>=4.5.0']
)
