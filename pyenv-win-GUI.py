# Author: primetime43
# GitHub: https://github.com/primetime43
__version__ = '1.2.0'

import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk

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
        root.after(0, _append_output, line)
    process.stdout.close()
    return process.wait()


def _set_busy(busy):
    state = tk.DISABLED if busy else tk.NORMAL
    for w in (install_button, uninstall_button, run_button, refresh_button, *quick_buttons):
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

    threading.Thread(target=worker, daemon=True).start()


# --- version querying --------------------------------------------------

def _parse_versions(text):
    out = []
    for line in text.splitlines():
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
root.geometry('720x640')
root.minsize(560, 480)
root.columnconfigure(0, weight=1)

# pyenv-win itself
pyenv_frame = ttk.LabelFrame(root, text='pyenv-win')
pyenv_frame.grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 5))

install_button = tk.Button(pyenv_frame, text='Install / Update pyenv-win', command=install_update)
install_button.pack(side=tk.LEFT, padx=6, pady=6)
uninstall_button = tk.Button(pyenv_frame, text='Uninstall pyenv-win', command=uninstall)
uninstall_button.pack(side=tk.LEFT, padx=(0, 6), pady=6)

# Quick actions
quick_frame = ttk.LabelFrame(root, text='Quick actions')
quick_frame.grid(row=1, column=0, sticky='ew', padx=10, pady=5)

quick_buttons = []
for text, key in QUICK_ACTIONS:
    btn = tk.Button(quick_frame, text=text, command=lambda k=key: quick_action(k))
    btn.pack(side=tk.LEFT, padx=6, pady=6)
    quick_buttons.append(btn)

# Command runner
runner_frame = ttk.LabelFrame(root, text='Run a pyenv command')
runner_frame.grid(row=2, column=0, sticky='ew', padx=10, pady=5)
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
output_frame.grid(row=3, column=0, sticky='nsew', padx=10, pady=5)
output_frame.rowconfigure(0, weight=1)
output_frame.columnconfigure(0, weight=1)
root.rowconfigure(3, weight=1)

output_text = tk.Text(output_frame, wrap='word', height=12)
output_text.grid(row=0, column=0, sticky='nsew', padx=(6, 0), pady=6)
scrollbar = tk.Scrollbar(output_frame, command=output_text.yview)
scrollbar.grid(row=0, column=1, sticky='ns', padx=(0, 6), pady=6)
output_text['yscrollcommand'] = scrollbar.set

# Footer
footer = tk.Frame(root)
footer.grid(row=4, column=0, sticky='ew', padx=10, pady=(5, 10))
footer.columnconfigure(0, weight=1)

status_var = tk.StringVar(value='Idle')
ttk.Label(footer, textvariable=status_var, anchor='w').grid(row=0, column=0, sticky='w')
tk.Button(footer, text='Clear output', command=clear_output).grid(row=0, column=1, sticky='e')

_on_command_changed()
# Prefetch installed versions so the dropdown is ready when the user opens it.
_query_versions('installed', lambda v: _apply_versions_to_arg('installed', v), silent=True)

root.mainloop()
