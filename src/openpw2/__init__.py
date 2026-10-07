"""Independent Icom IC-PW2 LAN reference implementation. Qt is optional."""

from .client import Client, ConnectionConfig
from .errors import AuthenticationError, CommandBlocked, ConnectionLost, ProtocolError

__version__ = "0.1.1"
__all__ = [
    "Client",
    "ConnectionConfig",
    "AuthenticationError",
    "CommandBlocked",
    "ConnectionLost",
    "ProtocolError",
]
