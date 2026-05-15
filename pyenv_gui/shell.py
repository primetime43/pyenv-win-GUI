"""Subprocess + output cleaning helpers. No Tk imports."""

from __future__ import annotations

import re
import subprocess


# pyenv-win colorizes some output with ANSI SGR codes. Tk renders them as
# garbage box characters, so we strip everywhere we surface subprocess output.
_ANSI_RE: re.Pattern[str] = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)


def first_version_line(text: str) -> str:
    """Return the first line that starts with a digit (a version), or ''.

    pyenv-win can prepend diagnostic lines like 'FATAL: ...' before the
    actual version, so we can't just take splitlines()[0].
    """
    for line in strip_ansi(text).splitlines():
        line = line.strip()
        if line and line[0].isdigit():
            return line
    return ''


def run_powershell(command: str, stream: bool = True) -> subprocess.Popen[str]:
    """Spawn `powershell -NoProfile -Command` with no console flash, UTF-8 text mode."""
    return subprocess.Popen(
        ['powershell', '-NoProfile', '-Command', command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
        encoding='utf-8',
        errors='replace',
        bufsize=1 if stream else -1,
    )
