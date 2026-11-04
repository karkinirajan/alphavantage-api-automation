"""A small Flask dashboard on the Alpha Vantage API."""

from .app import create_app

__all__ = ["__version__", "create_app"]
__version__ = "0.1.0"
