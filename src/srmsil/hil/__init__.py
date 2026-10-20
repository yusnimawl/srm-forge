"""Hardware-in-the-loop support: PC protocol, board links and sessions."""


class HilError(Exception):
    """A failure in the HIL link, a board or a session."""
