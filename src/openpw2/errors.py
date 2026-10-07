"""Public exceptions; messages never include authentication payloads."""


class PW2Error(Exception):
    """Base for errors applications may present to the operator."""


class ProtocolError(PW2Error):
    """Malformed or unsupported peer response."""


class AuthenticationError(PW2Error):
    """The peer rejected the login."""


class ConnectionLost(PW2Error):
    """Connection ended, timed out, or a command's result is uncertain."""


class CommandBlocked(PW2Error):
    """No request sent because current state does not permit the command."""
