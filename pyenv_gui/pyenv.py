"""pyenv-win adapters, version parsing, path detection, settings. No Tk imports."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .shell import strip_ansi


# Bundled official installer script. Vendored verbatim from
# https://raw.githubusercontent.com/pyenv-win/pyenv-win/master/pyenv-win/install-pyenv-win.ps1
# Refresh by re-downloading to pyenv_gui/install-pyenv-win.ps1.
INSTALL_SCRIPT_NAME: str = 'install-pyenv-win.ps1'

# Bundled window icon, accessed via importlib.resources (see App._set_window_icon).
ICON_NAME: str = 'main.ico'


# Friendly metadata for each pyenv subcommand. Key is the literal subcommand.
#   arg     : None | 'version' | 'command'
#   source  : where the version dropdown is populated from (only for arg='version')
COMMANDS: dict[str, dict[str, Any]] = {
    'install':      dict(label='Install Python version',           help='Download and install a Python version.',                                  arg='version', source='installable'),
    'uninstall':    dict(label='Uninstall Python version',         help='Remove an installed Python version.',                                     arg='version', source='installed'),
    'versions':     dict(label='List installed versions',          help='Show all Python versions installed via pyenv-win.',                       arg=None),
    'version':      dict(label='Show current version',             help='Show the currently active Python version and its origin.',                arg=None),
    'global':       dict(label='Set global Python version',        help='Set the system-wide default Python version.',                             arg='version', source='installed'),
    'local':        dict(label='Set local Python version',         help='Set the version for the current directory (.python-version).',            arg='version', source='installed'),
    'shell':        dict(label='Set shell Python version',         help='Set the version for the current shell session only.',                     arg='version', source='installed'),
    'rehash':       dict(label='Rehash shims',                     help='Rebuild pyenv shims after install or uninstall.',                         arg=None),
    'update':       dict(label='Update version mirrors',           help='Refresh the list of installable Python versions from the mirror.',        arg=None),
    'duplicate':    dict(label='Duplicate version',                help='Make a copy of an installed Python version under a new name.',            arg='version', source='installed'),
    'which':        dict(label='Locate executable (which)',        help='Show the full path to an executable for the active version.',             arg='command'),
    'whence':       dict(label='Find versions with executable',    help='List installed versions that contain a given executable.',                arg='command'),
    'exec':         dict(label='Exec with active Python',          help='Run a command using the currently active Python.',                        arg='command'),
    'vname':        dict(label='Show version name',                help='Print the active version name only.',                                     arg=None),
    'version-name': dict(label='Show version name (detailed)',     help='Print the active version name with origin info.',                         arg=None),
    'commands':     dict(label='List pyenv subcommands',           help='Show every available pyenv subcommand.',                                  arg=None),
}

COMMAND_ORDER: list[str] = [
    'install', 'uninstall', 'versions', 'version',
    'global', 'local', 'shell',
    'rehash', 'update', 'duplicate',
    'which', 'whence', 'exec',
    'vname', 'version-name', 'commands',
]

QUICK_ACTIONS: list[tuple[str, str]] = [
    ('Installed Versions', 'versions'),
    ('Current Version',    'version'),
    ('Rehash Shims',       'rehash'),
    ('Update Mirrors',     'update'),
]

LABEL_TO_KEY: dict[str, str] = {meta['label']: key for key, meta in COMMANDS.items()}


# Strict final-release pattern: X.Y.Z all numeric, no pre-release suffix.
_FINAL_VER_RE: re.Pattern[str] = re.compile(r'^\d+\.\d+\.\d+$')


def sort_versions_desc(versions: list[str]) -> list[str]:
    """Newest-first. Finals (3.12.0) beat their pre-releases (3.12.0rc1) at equal parts."""
    def key(v: str) -> tuple[tuple[int, ...], int, str]:
        if _FINAL_VER_RE.match(v):
            return (tuple(int(p) for p in v.split('.')), 1, '')
        nums = re.findall(r'\d+', v)
        parts = tuple(int(n) for n in nums[:3])
        while len(parts) < 3:
            parts = parts + (0,)
        return (parts, 0, v)
    return sorted(versions, key=key, reverse=True)


def parse_versions(text: str) -> list[str]:
    out: list[str] = []
    for line in strip_ansi(text).splitlines():
        line = line.strip()
        if not line or line.startswith(':'):
            continue
        if line.startswith('*'):
            line = line[1:].strip()
        first = line.split()[0] if line else ''
        if first and first[0].isdigit():
            out.append(first)
    return sort_versions_desc(out)


def extract_series(versions: list[str]) -> list[str]:
    """Unique major.minor series, sorted newest-first (e.g. ['3.13', '3.12', ...])."""
    series: set[str] = set()
    for v in versions:
        parts = v.split('.')
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            series.add(f'{parts[0]}.{parts[1]}')
    return sorted(series,
                  key=lambda s: tuple(int(x) for x in s.split('.')),
                  reverse=True)


def latest_in_series(versions: list[str], series: str) -> str | None:
    """Highest final-release patch in a major.minor series, or None."""
    prefix = series + '.'
    matching: list[tuple[tuple[int, ...], str]] = []
    for v in versions:
        if v.startswith(prefix) and _FINAL_VER_RE.match(v):
            matching.append((tuple(int(p) for p in v.split('.')), v))
    matching.sort()
    return matching[-1][1] if matching else None


def format_size(n: int) -> str:
    if n < 1024:
        return f'{n} B'
    if n < 1024 ** 2:
        return f'{n / 1024:.1f} KB'
    if n < 1024 ** 3:
        return f'{n / 1024 ** 2:.1f} MB'
    return f'{n / 1024 ** 3:.2f} GB'


def dir_size(path: str) -> int:
    """Walk a directory tree and sum file sizes. Ignores I/O errors."""
    total = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def pyenv_installed() -> bool:
    try:
        subprocess.check_output(
            ['powershell', '-NoProfile', '-Command', 'pyenv --version'],
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def persistent_path() -> str:
    """Read the user's effective persistent PATH (Machine + User) from the registry.

    We can't trust ``os.environ['PATH']`` because it was captured at GUI launch
    and won't reflect changes made by Fix PATH (or the official installer)
    during this session.
    """
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "$m=[Environment]::GetEnvironmentVariable('PATH','Machine');"
             "$u=[Environment]::GetEnvironmentVariable('PATH','User');"
             "Write-Output \"$m;$u\""],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            encoding='utf-8', errors='replace', timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return os.environ.get('PATH', '')


def check_pyenv_path() -> tuple[bool, str]:
    """Returns (ok, message). Looks for pyenv-win\\shims in PATH."""
    path = persistent_path()
    entries = [p.strip().lower() for p in path.split(';') if p.strip()]
    has_bin = any(r'pyenv-win\bin' in p for p in entries)
    has_shims = any(r'pyenv-win\shims' in p for p in entries)
    if not has_bin and not has_shims:
        return False, 'pyenv-win is not on PATH. After installing, open a new terminal so PATH updates take effect.'
    if not has_shims:
        return False, r'pyenv-win\shims is missing from PATH — `python` will not resolve to your selected version.'
    return True, ''


def get_pyenv_root() -> str | None:
    """Locate the pyenv-win install dir (the one containing 'versions/').

    Order: $env:PYENV (process env) → persistent USER env → default fallback.
    Returns None if no valid directory is found.
    """
    candidates: list[str] = []
    p = os.environ.get('PYENV')
    if p:
        candidates.append(p)
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "[Environment]::GetEnvironmentVariable('PYENV','User')"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            encoding='utf-8', errors='replace', timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            candidates.append(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    candidates.append(os.path.expandvars(r'%USERPROFILE%\.pyenv\pyenv-win'))
    for c in candidates:
        c = c.rstrip('\\/')
        if c and os.path.isdir(c):
            return c
    return None


# Settings sidecar — persists window geometry + last command across launches.
SETTINGS_PATH: Path = (
    Path(os.environ.get('APPDATA') or os.path.expanduser('~'))
    / 'pyenv-win-GUI' / 'settings.json'
)


def load_settings() -> dict[str, Any]:
    try:
        with SETTINGS_PATH.open('r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(data: dict[str, Any]) -> None:
    """Best-effort save; never raises out of the close handler."""
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with SETTINGS_PATH.open('w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


# PowerShell payload for the Fix PATH button. Prepends bin+shims to USER PATH
# (user scope = no admin required). Deduplicates if either is already present.
FIX_PATH_PS: str = r'''
$pyenv = $env:PYENV
if (-not $pyenv) { $pyenv = Join-Path $env:USERPROFILE '.pyenv\pyenv-win\' }
$pyenv = $pyenv.TrimEnd('\','/')
$bin   = Join-Path $pyenv 'bin'
$shims = Join-Path $pyenv 'shims'

if (-not (Test-Path $shims)) {
    Write-Output ('ERROR: Shims directory not found at ' + $shims)
    Write-Output 'Click "Install / Update pyenv-win" first.'
    exit 1
}

$userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
if (-not $userPath) { $userPath = '' }
$entries = @($userPath -split ';' | Where-Object { $_ })
$filtered = $entries | Where-Object {
    $t = $_.TrimEnd('\','/')
    $t -ne $bin -and $t -ne $shims
}
$newPath = (@($bin, $shims) + $filtered) -join ';'
[Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')

Write-Output 'USER PATH updated. Entries now at the front:'
Write-Output ('  ' + $bin)
Write-Output ('  ' + $shims)
Write-Output ''
Write-Output 'Already-open terminals will not see the change until restarted.'
Write-Output 'If a conflicting python.exe is in SYSTEM PATH, remove it via'
Write-Output 'System Properties > Environment Variables.'
'''
