"""
A jam's join code is its host's network address in base 36, so a friend's app
knows where to connect from the code alone: no IP addresses to configure.
"""

import socket
import string

DIGITS = string.digits + string.ascii_uppercase


def lan_ip():
    """This computer's address on its network (nothing is actually sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # picks the interface that reaches the internet
            return s.getsockname()[0]
    except OSError:  # offline: friends can't reach us anyway, but this PC still can
        return "127.0.0.1"


def code_for(ip):
    """'192.168.68.56' -> its 7-character join code."""
    n = int.from_bytes(socket.inet_aton(ip), "big")
    code = ""
    for _ in range(7):  # 36**7 > 2**32: every IPv4 address fits
        n, digit = divmod(n, 36)
        code = DIGITS[digit] + code
    return code


def host_for(code):
    """The host address inside a join code; ValueError for a typo."""
    try:
        return socket.inet_ntoa(int(code.strip(), 36).to_bytes(4, "big"))
    except (ValueError, OverflowError):
        raise ValueError("That code doesn't look right") from None
