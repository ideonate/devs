"""Web Admin UI for DevContainer Management."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("devs-webadmin")
except PackageNotFoundError:
    __version__ = "0.0.0"
__author__ = "Dan Lester"
__email__ = "dan@ideonate.com"
