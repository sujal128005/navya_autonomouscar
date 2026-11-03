"""Read one key press without waiting for ENTER: Windows console, or Linux terminal (also over SSH).

    from keyboard_input import read_key
    key = read_key()      # "q", "a", "\\r" (ENTER), ... or None when nothing was pressed

Never blocks, so control loops keep running (and keep talking to the Arduino) while waiting.
"""

import atexit
import os
import sys

if os.name == "nt":
    import msvcrt

    def read_key() -> str | None:
        if msvcrt.kbhit():
            return msvcrt.getwch().lower()
        return None
else:
    import select
    import termios
    import tty

    _saved = None

    def _restore():
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _saved)

    def read_key() -> str | None:
        global _saved
        if not sys.stdin.isatty():
            return None
        if _saved is None:
            # Keys arrive one at a time; Ctrl+C still works. The terminal is restored on exit.
            _saved = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
            atexit.register(_restore)
        if select.select([sys.stdin], [], [], 0)[0]:
            key = sys.stdin.read(1).lower()
            return "\r" if key == "\n" else key
        return None
