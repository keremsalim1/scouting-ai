"""Console encoding helper.

On Windows, ``sys.stdout`` defaults to the ANSI code page (cp1254 on a Turkish
system), so printing any non-ASCII character raises UnicodeEncodeError. Our
report text legitimately contains Turkish letters and typographic symbols
(the feature flag ``gol / G-xG analizleri`` uses U+2212 MINUS SIGN), which
means every script that prints results would crash for a fresh clone.

Setting PYTHONIOENCODING in the shell also fixes it, but then the code only
works for people who know to do that. Reconfiguring the stream in-process
makes it work everywhere, including under `make`, which passes no environment.
"""

from __future__ import annotations

import sys


def force_utf8() -> None:
    """Make stdout/stderr UTF-8, replacing anything the terminal cannot show.

    ``errors="replace"`` rather than ``"strict"``: a console that genuinely
    cannot render a glyph should print a placeholder, not abort a 40-second
    data load.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
