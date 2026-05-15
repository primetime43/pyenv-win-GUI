# Author: primetime43
# GitHub: https://github.com/primetime43
__version__ = '2.0.0'

import os
import re
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk

# pyenv-win colorizes some output with ANSI SGR codes. Tk has no idea what
# those are and renders them as garbage. Strip them everywhere we surface
# subprocess output.
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')


def _strip_ansi(text):
    return _ANSI_RE.sub('', text)


def _first_version_line(text):
    """Return the first line that starts with a digit (a version), or ''.

    pyenv-win can prepend diagnostic lines like 'FATAL: ...' before the
    actual version, so we can't just take splitlines()[0].
    """
    for line in _strip_ansi(text).splitlines():
        line = line.strip()
        if line and line[0].isdigit():
            return line
    return ''

INSTALL_SCRIPT_URL = (
    'https://raw.githubusercontent.com/pyenv-win/pyenv-win/master/'
    'pyenv-win/install-pyenv-win.ps1'
)
INSTALL_SCRIPT_PATH = './install-pyenv-win.ps1'

# Friendly metadata for each pyenv subcommand. Key is the literal subcommand.
#   arg     : None | 'version' | 'command'
#   source  : where the version dropdown is populated from (only for arg='version')
COMMANDS = {
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

COMMAND_ORDER = [
    'install', 'uninstall', 'versions', 'version',
    'global', 'local', 'shell',
    'rehash', 'update', 'duplicate',
    'which', 'whence', 'exec',
    'vname', 'version-name', 'commands',
]

QUICK_ACTIONS = [
    ('Installed Versions', 'versions'),
    ('Current Version',    'version'),
    ('Rehash Shims',       'rehash'),
    ('Update Mirrors',     'update'),
]

LABEL_TO_KEY = {meta['label']: key for key, meta in COMMANDS.items()}

# None = not yet loaded. Populated lazily and invalidated after install/uninstall.
_versions_cache = {'installed': None, 'installable': None}


# --- subprocess plumbing -----------------------------------------------

def _run_powershell(command, stream=True):
    return subprocess.Popen(
        ['powershell', '-NoProfile', '-Command', command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
        encoding='utf-8',
        errors='replace',
        bufsize=1 if stream else -1,
    )


def _append_output(text):
    output_text.insert(tk.END, text)
    output_text.see(tk.END)


def _stream_to_output(process):
    for line in iter(process.stdout.readline, ''):
        root.after(0, _append_output, _strip_ansi(line))
    process.stdout.close()
    return process.wait()


def _set_busy(busy):
    state = tk.DISABLED if busy else tk.NORMAL
    for w in (install_button, uninstall_button, run_button, refresh_button,
              refresh_status_button, fix_path_button, *quick_buttons):
        w.config(state=state)
    status_var.set('Running…' if busy else 'Idle')


def _with_busy(task):
    _set_busy(True)

    def worker():
        try:
            task()
        except Exception as e:
            root.after(0, _append_output, f'Error: {e}\n')
        finally:
            root.after(0, _set_busy, False)
            # State may have changed (install/uninstall/global/local/shell);
            # refresh the status panel after every command.
            root.after(0, _refresh_status)

    threading.Thread(target=worker, daemon=True).start()


# --- status (active version + scope panel + PATH check) ----------------

def _format_scope_value(output, returncode):
    """pyenv {global,local,shell} with no args prints the value or an error.

    pyenv-win may prepend warning lines (e.g. FATAL diagnostics), so we walk
    lines for the first version-shaped one rather than taking splitlines()[0].
    """
    if returncode != 0:
        return '(not set)'
    line = _first_version_line(output)
    if not line:
        return '(not set)'
    # `pyenv global` etc. typically prints just the version; if extra text
    # follows (unlikely), keep only the first token.
    return line.split()[0]


def _persistent_path():
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


def _check_pyenv_path():
    """Returns (ok: bool, message: str). Looks for pyenv-win\\shims in PATH."""
    path = _persistent_path()
    entries = [p.strip().lower() for p in path.split(';') if p.strip()]
    has_bin = any(r'pyenv-win\bin' in p for p in entries)
    has_shims = any(r'pyenv-win\shims' in p for p in entries)
    if not has_bin and not has_shims:
        return False, 'pyenv-win is not on PATH. After installing, open a new terminal so PATH updates take effect.'
    if not has_shims:
        return False, r'pyenv-win\shims is missing from PATH — `python` will not resolve to your selected version.'
    return True, ''


# PowerShell payload for the Fix PATH button. Prepends bin+shims to USER PATH
# (user scope = no admin required). Deduplicates if either is already present.
_FIX_PATH_PS = r'''
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


def _fix_path():
    if not messagebox.askyesno(
        'Fix pyenv-win PATH',
        'This will prepend pyenv-win\\bin and pyenv-win\\shims to your USER PATH '
        'so that `python` and the other shims resolve to your pyenv-managed version.\n\n'
        'Caveats:\n'
        '  • Already-open terminals won\'t see the change until they restart.\n'
        '  • If a conflicting Python is in SYSTEM PATH, you\'ll need to remove '
        'it manually via System Properties > Environment Variables.\n\n'
        'Continue?'
    ):
        return

    def task():
        root.after(0, _append_output, '> Fix pyenv-win PATH (USER scope)\n')
        proc = _run_powershell(_FIX_PATH_PS)
        rc = _stream_to_output(proc)
        # Update this process's own PATH so any subsequent pyenv calls from
        # this GUI session see the new shims. The persistent change is what
        # matters for new terminals; this matters for the current GUI.
        if rc == 0:
            new_path = _persistent_path()
            if new_path:
                os.environ['PATH'] = new_path

    _with_busy(task)


def _show_path_warning(msg):
    path_warning_var.set(f'⚠ {msg}')
    path_row.grid()


def _hide_path_warning():
    path_warning_var.set('')
    path_row.grid_remove()


def _refresh_status():
    """Re-query pyenv for active/global/local/shell and refresh PATH warning."""

    def task():
        # Kick off all four queries in parallel — Popen returns immediately,
        # the subprocesses run concurrently, communicate() then collects.
        procs = {
            'active': _run_powershell('pyenv version', stream=False),
            'global': _run_powershell('pyenv global', stream=False),
            'local':  _run_powershell('pyenv local', stream=False),
            'shell':  _run_powershell('pyenv shell', stream=False),
        }
        results = {}
        for name, p in procs.items():
            try:
                out, _ = p.communicate(timeout=10)
                results[name] = (p.returncode, out)
            except subprocess.TimeoutExpired:
                p.kill()
                results[name] = (-1, '')

        rc_a, out_a = results['active']
        if rc_a != 0 and not out_a.strip():
            active = '(pyenv-win not detected)'
        else:
            active = _first_version_line(out_a) or '(unknown)'
        root.after(0, active_var.set, f'Active: {active}')

        rc, out = results['global']
        root.after(0, global_var.set, f'Global: {_format_scope_value(out, rc)}')

        rc, out = results['local']
        root.after(0, local_var.set, f'Local: {_format_scope_value(out, rc)}')

        rc, out = results['shell']
        root.after(0, shell_var.set, f'Shell: {_format_scope_value(out, rc)}')

        ok, msg = _check_pyenv_path()
        if rc_a != 0:
            root.after(0, _show_path_warning,
                       'pyenv-win is not installed or not on PATH. Use "Install / Update pyenv-win" below.')
        elif not ok:
            root.after(0, _show_path_warning, msg)
        else:
            root.after(0, _hide_path_warning)

    threading.Thread(target=task, daemon=True).start()


# --- version querying --------------------------------------------------

def _parse_versions(text):
    out = []
    for line in _strip_ansi(text).splitlines():
        line = line.strip()
        if not line or line.startswith(':'):
            continue
        if line.startswith('*'):
            line = line[1:].strip()
        first = line.split()[0] if line else ''
        if first and first[0].isdigit():
            out.append(first)
    return out


def _query_versions(kind, on_done, silent=False):
    cmd = 'pyenv versions' if kind == 'installed' else 'pyenv install -l'

    def task():
        try:
            proc = _run_powershell(cmd, stream=False)
            out, _ = proc.communicate()
        except FileNotFoundError:
            root.after(0, on_done, [])
            return
        if proc.returncode != 0:
            if not silent:
                root.after(0, _append_output, f'Failed to load {kind} versions.\n')
            root.after(0, on_done, [])
            return
        versions = _parse_versions(out)
        _versions_cache[kind] = versions
        root.after(0, on_done, versions)

    threading.Thread(target=task, daemon=True).start()


def _apply_versions_to_arg(kind, versions):
    """Only update the args combobox if the current command actually wants this list."""
    key = _current_command_key()
    if not key:
        return
    if COMMANDS[key].get('source') == kind:
        arg_entry.config(values=versions)


def _refresh_versions():
    key = _current_command_key()
    if not key:
        return
    source = COMMANDS[key].get('source')
    if not source:
        return
    _versions_cache[source] = None
    _append_output(f'Refreshing {source} versions…\n')
    _query_versions(source, lambda v: _apply_versions_to_arg(source, v))


# --- command form ------------------------------------------------------

def _current_command_key():
    return LABEL_TO_KEY.get(command_var.get(), '')


def _on_command_changed(*_):
    key = _current_command_key()
    if not key:
        return
    meta = COMMANDS[key]
    help_var.set(meta['help'])
    arg_var.set('')

    if meta['arg'] is None:
        arg_label.config(text='(no arguments)')
        arg_entry.config(state='disabled', values=())
        refresh_button.grid_remove()
    elif meta['arg'] == 'version':
        arg_label.config(text='Version:')
        arg_entry.config(state='normal')
        source = meta['source']
        cached = _versions_cache[source]
        if cached is not None:
            arg_entry.config(values=cached)
        else:
            arg_entry.config(values=())
            _query_versions(source, lambda v: _apply_versions_to_arg(source, v))
        refresh_button.grid()
    elif meta['arg'] == 'command':
        arg_label.config(text='Command:')
        arg_entry.config(state='normal', values=())
        refresh_button.grid_remove()


def _run_pyenv_subcommand(key, args=''):
    cmdline = f'pyenv {key} {args}'.strip()

    def task():
        root.after(0, _append_output, f'> {cmdline}\n')
        proc = _run_powershell(cmdline)
        _stream_to_output(proc)
        if key in ('install', 'uninstall', 'duplicate'):
            _versions_cache['installed'] = None
            _query_versions('installed',
                            lambda v: _apply_versions_to_arg('installed', v),
                            silent=True)

    _with_busy(task)


def run_command():
    key = _current_command_key()
    if not key:
        return
    meta = COMMANDS[key]
    args = arg_var.get().strip() if meta['arg'] else ''
    if meta['arg'] and not args:
        _append_output(f'Provide a {meta["arg"]} for "{meta["label"]}".\n')
        return
    _run_pyenv_subcommand(key, args)


def quick_action(key):
    _run_pyenv_subcommand(key)


def clear_output():
    output_text.delete('1.0', tk.END)


# --- pyenv-win itself (re-runs the official installer script) ----------

def _pyenv_installed():
    try:
        subprocess.check_output(
            ['powershell', '-NoProfile', '-Command', 'pyenv --version'],
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _ensure_install_script():
    if os.path.exists(INSTALL_SCRIPT_PATH):
        return True
    root.after(0, _append_output, 'Downloading installer script…\n')
    ps = (
        f'Invoke-WebRequest -UseBasicParsing -Uri "{INSTALL_SCRIPT_URL}" '
        f'-OutFile "{INSTALL_SCRIPT_PATH}"'
    )
    result = subprocess.run(
        ['powershell', '-NoProfile', '-Command', ps],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
        encoding='utf-8', errors='replace',
    )
    if result.returncode != 0:
        root.after(0, _append_output, 'Failed to download installer script.\n')
        if result.stdout:
            root.after(0, _append_output, result.stdout)
        return False
    return True


def install_update():
    def task():
        if _pyenv_installed():
            root.after(0, _append_output,
                       'pyenv-win is already installed; running installer will update it.\n')
        if not _ensure_install_script():
            return
        root.after(0, _append_output, 'Starting installation…\n')
        proc = _run_powershell(f'& "{INSTALL_SCRIPT_PATH}"')
        _stream_to_output(proc)
    _with_busy(task)


def uninstall():
    def task():
        if not _pyenv_installed():
            root.after(0, _append_output,
                       'pyenv-win is not installed, nothing to uninstall.\n')
            return
        if not _ensure_install_script():
            return
        root.after(0, _append_output, 'Starting uninstallation…\n')
        proc = _run_powershell(f'& "{INSTALL_SCRIPT_PATH}" -Uninstall')
        _stream_to_output(proc)
    _with_busy(task)


# --- UI ----------------------------------------------------------------

root = tk.Tk()
root.title(f'pyenv-win GUI - Version {__version__}')
root.geometry('720x720')
root.minsize(560, 540)
root.columnconfigure(0, weight=1)

# Status: active version + three-scope panel + PATH warning
status_frame = ttk.LabelFrame(root, text='Status')
status_frame.grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 5))
status_frame.columnconfigure(0, weight=1)

status_top = tk.Frame(status_frame)
status_top.grid(row=0, column=0, sticky='ew', padx=8, pady=(6, 2))
status_top.columnconfigure(0, weight=1)

active_var = tk.StringVar(value='Active: (loading…)')
ttk.Label(status_top, textvariable=active_var,
          font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky='w')
refresh_status_button = tk.Button(status_top, text='↻ Refresh', command=lambda: _refresh_status())
refresh_status_button.grid(row=0, column=1, sticky='e')

scopes_frame = tk.Frame(status_frame)
scopes_frame.grid(row=1, column=0, sticky='ew', padx=8, pady=(0, 4))
for i in range(3):
    scopes_frame.columnconfigure(i, weight=1, uniform='scope')

global_var = tk.StringVar(value='Global: …')
local_var = tk.StringVar(value='Local: …')
shell_var = tk.StringVar(value='Shell: …')
ttk.Label(scopes_frame, textvariable=global_var).grid(row=0, column=0, sticky='w')
ttk.Label(scopes_frame, textvariable=local_var).grid(row=0, column=1, sticky='w')
ttk.Label(scopes_frame, textvariable=shell_var).grid(row=0, column=2, sticky='w')

path_row = tk.Frame(status_frame)
path_row.grid(row=2, column=0, sticky='ew', padx=8, pady=(0, 6))
path_row.columnconfigure(0, weight=1)
path_row.grid_remove()

path_warning_var = tk.StringVar(value='')
path_warning_label = ttk.Label(path_row, textvariable=path_warning_var,
                               foreground='#c0392b', wraplength=540, justify='left')
path_warning_label.grid(row=0, column=0, sticky='w')

fix_path_button = tk.Button(path_row, text='Fix PATH', command=_fix_path)
fix_path_button.grid(row=0, column=1, sticky='e', padx=(8, 0))

# pyenv-win itself
pyenv_frame = ttk.LabelFrame(root, text='pyenv-win')
pyenv_frame.grid(row=1, column=0, sticky='ew', padx=10, pady=5)

install_button = tk.Button(pyenv_frame, text='Install / Update pyenv-win', command=install_update)
install_button.pack(side=tk.LEFT, padx=6, pady=6)
uninstall_button = tk.Button(pyenv_frame, text='Uninstall pyenv-win', command=uninstall)
uninstall_button.pack(side=tk.LEFT, padx=(0, 6), pady=6)

# Quick actions
quick_frame = ttk.LabelFrame(root, text='Quick actions')
quick_frame.grid(row=2, column=0, sticky='ew', padx=10, pady=5)

quick_buttons = []
for text, key in QUICK_ACTIONS:
    btn = tk.Button(quick_frame, text=text, command=lambda k=key: quick_action(k))
    btn.pack(side=tk.LEFT, padx=6, pady=6)
    quick_buttons.append(btn)

# Command runner
runner_frame = ttk.LabelFrame(root, text='Run a pyenv command')
runner_frame.grid(row=3, column=0, sticky='ew', padx=10, pady=5)
runner_frame.columnconfigure(1, weight=1)

ttk.Label(runner_frame, text='Command:').grid(row=0, column=0, sticky='w', padx=(8, 4), pady=(8, 2))

command_labels = [COMMANDS[k]['label'] for k in COMMAND_ORDER]
command_var = tk.StringVar(value=command_labels[0])
command_menu = ttk.Combobox(runner_frame, textvariable=command_var, values=command_labels, state='readonly')
command_menu.grid(row=0, column=1, columnspan=2, sticky='ew', padx=(0, 8), pady=(8, 2))
command_menu.bind('<<ComboboxSelected>>', _on_command_changed)

help_var = tk.StringVar()
help_label = ttk.Label(runner_frame, textvariable=help_var, foreground='#555',
                       wraplength=620, justify='left')
help_label.grid(row=1, column=0, columnspan=3, sticky='w', padx=8, pady=(0, 4))

arg_label = ttk.Label(runner_frame, text='')
arg_label.grid(row=2, column=0, sticky='w', padx=(8, 4), pady=(0, 8))

arg_var = tk.StringVar()
arg_entry = ttk.Combobox(runner_frame, textvariable=arg_var)
arg_entry.grid(row=2, column=1, sticky='ew', padx=(0, 4), pady=(0, 8))
arg_entry.bind('<Return>', lambda _e: run_command())

refresh_button = tk.Button(runner_frame, text='Refresh', command=_refresh_versions)
refresh_button.grid(row=2, column=2, sticky='e', padx=(0, 8), pady=(0, 8))
refresh_button.grid_remove()

run_button = tk.Button(runner_frame, text='Run', command=run_command, width=12)
run_button.grid(row=3, column=0, columnspan=3, pady=(0, 8))

# Output
output_frame = ttk.LabelFrame(root, text='Output')
output_frame.grid(row=4, column=0, sticky='nsew', padx=10, pady=5)
output_frame.rowconfigure(0, weight=1)
output_frame.columnconfigure(0, weight=1)
root.rowconfigure(4, weight=1)

output_text = tk.Text(output_frame, wrap='word', height=12)
output_text.grid(row=0, column=0, sticky='nsew', padx=(6, 0), pady=6)
scrollbar = tk.Scrollbar(output_frame, command=output_text.yview)
scrollbar.grid(row=0, column=1, sticky='ns', padx=(0, 6), pady=6)
output_text['yscrollcommand'] = scrollbar.set

# Footer
footer = tk.Frame(root)
footer.grid(row=5, column=0, sticky='ew', padx=10, pady=(5, 10))
footer.columnconfigure(0, weight=1)

status_var = tk.StringVar(value='Idle')
ttk.Label(footer, textvariable=status_var, anchor='w').grid(row=0, column=0, sticky='w')
tk.Button(footer, text='Clear output', command=clear_output).grid(row=0, column=1, sticky='e')

_on_command_changed()
# Prefetch installed versions so the dropdown is ready when the user opens it.
_query_versions('installed', lambda v: _apply_versions_to_arg('installed', v), silent=True)
# Populate the status panel.
_refresh_status()

root.mainloop()
