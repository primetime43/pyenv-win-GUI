"""Main application — the App class owns the root window and all widget state.

Public surface used by dialogs:
- app.root                   : tk.Tk
- app.is_busy                : bool re-entry guard
- app.append_output(text)
- app.run_external(label, command_str, on_complete=None)
- app.run_pyenv_subcommand(key, args='')
- app.current_active_version() -> str | None
- app.refresh_status()
- app.query_versions(kind, on_done, silent=False)
"""

import os
import re
import subprocess
import threading
import tkinter as tk
from importlib.resources import as_file, files
from tkinter import filedialog, messagebox, ttk

from . import dialogs
from . import pyenv as pyenv_mod
from .shell import first_version_line, run_powershell, strip_ansi
from .tooltip import Tooltip


# pyenv-win marks output phases with bracketed tags like "::  [Downloading] ::".
# (Percent-based progress was considered but pyenv-win's install path uses
# Invoke-WebRequest -UseBasicParsing, which never emits percents to stdout, so
# the progress bar stays indeterminate throughout.)
_PHASE_RE = re.compile(r'::\s*\[([^]]+)\]')


class App:
    def __init__(self):
        self.is_busy = False
        self.versions_cache = {'installed': None, 'installable': None}
        # Tracks the active subprocess so the Stop button can taskkill it.
        self._current_process = None
        self._build_ui()
        self._apply_settings()
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

        # Initial populate.
        self._on_command_changed()
        self.query_versions(
            'installed',
            lambda v: self._apply_versions_to_arg('installed', v),
            silent=True,
        )
        # Prefetch installable so the "Install Python 3.X" buttons populate
        # shortly after launch.
        self.query_versions(
            'installable',
            self._on_installable_loaded,
            silent=True,
        )
        self.refresh_status()

    def _on_installable_loaded(self, versions):
        self._apply_versions_to_arg('installable', versions)
        self._rebuild_install_latest_buttons()

    def run(self):
        self.root.mainloop()

    # ----- UI construction --------------------------------------------

    def _set_window_icon(self):
        """Set the window icon for the root and all Toplevels (default=).

        When frozen by PyInstaller (built with --icon) the icon is embedded in
        the exe, so sys.executable is the bitmap source. From source we resolve
        the bundled .ico via importlib.resources — robust regardless of the
        current working directory. Failures are swallowed: a missing or invalid
        icon must never block UI construction.
        """
        import sys
        try:
            if getattr(sys, 'frozen', False):
                self.root.iconbitmap(default=sys.executable)
            else:
                ref = files('pyenv_gui').joinpath(pyenv_mod.ICON_NAME)
                with as_file(ref) as ico:
                    self.root.iconbitmap(default=str(ico))
        except Exception:
            pass

    def _build_ui(self):
        from . import __version__

        self.root = tk.Tk()
        self.root.title(f'pyenv-win GUI - Version {__version__}')
        self.root.geometry('720x720')
        self.root.minsize(560, 540)
        self.root.columnconfigure(0, weight=1)

        self._set_window_icon()

        # Status frame
        status_frame = ttk.LabelFrame(self.root, text='Status')
        status_frame.grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 5))
        status_frame.columnconfigure(0, weight=1)

        status_top = tk.Frame(status_frame)
        status_top.grid(row=0, column=0, sticky='ew', padx=8, pady=(6, 2))
        status_top.columnconfigure(0, weight=1)

        self.active_var = tk.StringVar(value='Active: (loading…)')
        ttk.Label(status_top, textvariable=self.active_var,
                  font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky='w')
        self.refresh_status_button = tk.Button(status_top, text='↻ Refresh',
                                               command=self.refresh_status)
        self.refresh_status_button.grid(row=0, column=1, sticky='e')
        Tooltip(self.refresh_status_button,
                'Re-query the active version, scope panel, and PATH check.')

        scopes_frame = tk.Frame(status_frame)
        scopes_frame.grid(row=1, column=0, sticky='ew', padx=8, pady=(0, 4))
        for i in range(3):
            scopes_frame.columnconfigure(i, weight=1, uniform='scope')

        self.global_var = tk.StringVar(value='Global: …')
        self.local_var = tk.StringVar(value='Local: …')
        self.shell_var = tk.StringVar(value='Shell: …')
        ttk.Label(scopes_frame, textvariable=self.global_var).grid(row=0, column=0, sticky='w')
        ttk.Label(scopes_frame, textvariable=self.local_var).grid(row=0, column=1, sticky='w')
        ttk.Label(scopes_frame, textvariable=self.shell_var).grid(row=0, column=2, sticky='w')

        self.path_row = tk.Frame(status_frame)
        self.path_row.grid(row=2, column=0, sticky='ew', padx=8, pady=(0, 6))
        self.path_row.columnconfigure(0, weight=1)
        self.path_row.grid_remove()

        self.path_warning_var = tk.StringVar(value='')
        ttk.Label(self.path_row, textvariable=self.path_warning_var,
                  foreground='#c0392b', wraplength=540, justify='left').grid(
            row=0, column=0, sticky='w')

        self.fix_path_button = tk.Button(self.path_row, text='Fix PATH',
                                         command=self._fix_path)
        self.fix_path_button.grid(row=0, column=1, sticky='e', padx=(8, 0))
        Tooltip(self.fix_path_button,
                'Prepend pyenv-win\\bin and pyenv-win\\shims to your USER PATH\n'
                "so 'python' resolves to your pyenv-managed version.")

        # pyenv-win itself
        pyenv_frame = ttk.LabelFrame(self.root, text='pyenv-win')
        pyenv_frame.grid(row=1, column=0, sticky='ew', padx=10, pady=5)

        self.install_button = tk.Button(pyenv_frame, text='Install / Update pyenv-win',
                                        command=self._install_update)
        self.install_button.pack(side=tk.LEFT, padx=6, pady=6)
        Tooltip(self.install_button,
                "Install pyenv-win, or update it if already installed.")
        self.uninstall_button = tk.Button(pyenv_frame, text='Uninstall pyenv-win',
                                          command=self._uninstall_pyenv)
        self.uninstall_button.pack(side=tk.LEFT, padx=(0, 6), pady=6)
        Tooltip(self.uninstall_button,
                "Remove pyenv-win from your system (including its env vars).")
        self.open_root_button = tk.Button(pyenv_frame, text='Open pyenv root',
                                          command=self._open_pyenv_root)
        self.open_root_button.pack(side=tk.LEFT, padx=(0, 6), pady=6)
        Tooltip(self.open_root_button,
                'Open the pyenv-win install directory in Explorer.')

        # Quick actions
        quick_frame = ttk.LabelFrame(self.root, text='Quick actions')
        quick_frame.grid(row=2, column=0, sticky='ew', padx=10, pady=5)

        self.quick_buttons = []
        for text, key in pyenv_mod.QUICK_ACTIONS:
            btn = tk.Button(quick_frame, text=text,
                            command=lambda k=key: self.run_pyenv_subcommand(k))
            btn.pack(side=tk.LEFT, padx=6, pady=6)
            # Reuse the help string already living in COMMANDS metadata.
            Tooltip(btn, pyenv_mod.COMMANDS[key]['help'])
            self.quick_buttons.append(btn)

        manage_button = tk.Button(quick_frame, text='Manage installed…',
                                  command=lambda: dialogs.open_manage_dialog(self))
        manage_button.pack(side=tk.LEFT, padx=6, pady=6)
        Tooltip(manage_button,
                'Manage installed Python versions: set global, uninstall,\n'
                'create venv, manage pip packages, open folder.')
        self.quick_buttons.append(manage_button)

        # Install Python (latest stable per series + Browse dialog)
        self.install_python_frame = ttk.LabelFrame(self.root, text='Install Python')
        self.install_python_frame.grid(row=3, column=0, sticky='ew', padx=10, pady=5)

        # Browse first so it pins to the right; dynamic per-series buttons pack
        # in between with side=LEFT.
        self.browse_button = tk.Button(
            self.install_python_frame, text='Browse all…',
            command=lambda: dialogs.open_browse_dialog(self),
        )
        self.browse_button.pack(side=tk.RIGHT, padx=6, pady=6)
        Tooltip(self.browse_button,
                'Browse and search every installable Python version,\n'
                'with filters and an already-installed marker.')

        self.install_latest_label = ttk.Label(
            self.install_python_frame, text='Loading installable versions…',
            foreground='#888',
        )
        self.install_latest_label.pack(side=tk.LEFT, padx=(8, 4), pady=6)
        self.install_latest_buttons = []  # rebuilt by _rebuild_install_latest_buttons

        # Command runner
        runner_frame = ttk.LabelFrame(self.root, text='Run a pyenv command')
        runner_frame.grid(row=4, column=0, sticky='ew', padx=10, pady=5)
        runner_frame.columnconfigure(1, weight=1)

        ttk.Label(runner_frame, text='Command:').grid(
            row=0, column=0, sticky='w', padx=(8, 4), pady=(8, 2))

        self.command_labels = [pyenv_mod.COMMANDS[k]['label'] for k in pyenv_mod.COMMAND_ORDER]
        self.command_var = tk.StringVar(value=self.command_labels[0])
        command_menu = ttk.Combobox(runner_frame, textvariable=self.command_var,
                                    values=self.command_labels, state='readonly')
        command_menu.grid(row=0, column=1, columnspan=2, sticky='ew',
                          padx=(0, 8), pady=(8, 2))
        command_menu.bind('<<ComboboxSelected>>', self._on_command_changed)

        self.help_var = tk.StringVar()
        ttk.Label(runner_frame, textvariable=self.help_var, foreground='#555',
                  wraplength=620, justify='left').grid(
            row=1, column=0, columnspan=3, sticky='w', padx=8, pady=(0, 4))

        self.arg_label = ttk.Label(runner_frame, text='')
        self.arg_label.grid(row=2, column=0, sticky='w', padx=(8, 4), pady=(0, 8))

        self.arg_var = tk.StringVar()
        self.arg_entry = ttk.Combobox(runner_frame, textvariable=self.arg_var)
        self.arg_entry.grid(row=2, column=1, sticky='ew', padx=(0, 4), pady=(0, 8))
        self.arg_entry.bind('<Return>', lambda _e: self._run_command())

        self.refresh_button = tk.Button(runner_frame, text='Refresh',
                                        command=self._refresh_versions)
        self.refresh_button.grid(row=2, column=2, sticky='e', padx=(0, 8), pady=(0, 8))
        self.refresh_button.grid_remove()
        Tooltip(self.refresh_button,
                'Force re-fetch the version list from pyenv.')

        self.run_button = tk.Button(runner_frame, text='Run',
                                    command=self._run_command, width=12)
        self.run_button.grid(row=3, column=0, columnspan=3, pady=(0, 8))
        Tooltip(self.run_button,
                'Run the selected pyenv subcommand with the argument above.')

        # Output
        output_frame = ttk.LabelFrame(self.root, text='Output')
        output_frame.grid(row=5, column=0, sticky='nsew', padx=10, pady=5)
        output_frame.rowconfigure(0, weight=1)
        output_frame.columnconfigure(0, weight=1)
        self.root.rowconfigure(5, weight=1)

        self.output_text = tk.Text(output_frame, wrap='word', height=12)
        self.output_text.grid(row=0, column=0, sticky='nsew', padx=(6, 0), pady=6)
        out_scroll = tk.Scrollbar(output_frame, command=self.output_text.yview)
        out_scroll.grid(row=0, column=1, sticky='ns', padx=(0, 6), pady=6)
        self.output_text['yscrollcommand'] = out_scroll.set
        self._install_output_context_menu()

        # Progress (hidden when idle)
        self.progress_frame = tk.Frame(self.root)
        self.progress_frame.grid(row=6, column=0, sticky='ew', padx=10, pady=(2, 0))
        self.progress_frame.columnconfigure(0, weight=1)
        self.progress_frame.grid_remove()

        self.progress_bar = ttk.Progressbar(self.progress_frame, mode='indeterminate')
        self.progress_bar.grid(row=0, column=0, sticky='ew')

        self.progress_phase_var = tk.StringVar(value='')
        ttk.Label(self.progress_frame, textvariable=self.progress_phase_var,
                  foreground='#555').grid(row=0, column=1, sticky='w', padx=(8, 0))

        # Stop button is only relevant while busy; lives in the progress frame
        # so it auto-hides via grid_remove() in _set_busy(False). Intentionally
        # NOT in the busy-button disable list — Stop only matters when busy.
        self.stop_button = tk.Button(self.progress_frame, text='Stop',
                                      command=self._stop_current)
        self.stop_button.grid(row=0, column=2, sticky='e', padx=(8, 0))
        Tooltip(self.stop_button,
                'Force-terminate the running operation and its child processes.')

        # Footer
        footer = tk.Frame(self.root)
        footer.grid(row=7, column=0, sticky='ew', padx=10, pady=(5, 10))
        footer.columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(value='Idle')
        ttk.Label(footer, textvariable=self.status_var, anchor='w').grid(
            row=0, column=0, sticky='w')
        tk.Button(footer, text='Clear output',
                  command=lambda: self.output_text.delete('1.0', tk.END)).grid(
            row=0, column=1, sticky='e')

    def _apply_settings(self):
        settings = pyenv_mod.load_settings()
        geom = settings.get('geometry')
        applied = False
        if isinstance(geom, str):
            try:
                self.root.geometry(geom)
                applied = True
            except tk.TclError:
                pass
        # No (or invalid) saved position — center on screen for first launch.
        if not applied:
            dialogs.center_window(self.root)
        last_cmd = settings.get('last_command')
        if isinstance(last_cmd, str) and last_cmd in self.command_labels:
            self.command_var.set(last_cmd)

    def _on_close(self):
        pyenv_mod.save_settings({
            'geometry': self.root.geometry(),
            'last_command': self.command_var.get(),
        })
        self.root.destroy()

    # ----- Output & busy state ----------------------------------------

    def append_output(self, text):
        self.output_text.insert(tk.END, text)
        self.output_text.see(tk.END)

    def _install_output_context_menu(self):
        """Right-click menu on the Output Text widget: Copy / Copy all / Save / Clear."""
        menu = tk.Menu(self.output_text, tearoff=0)
        menu.add_command(label='Copy', command=self._copy_output_selection)
        menu.add_command(label='Copy all', command=self._copy_output_all)
        menu.add_separator()
        menu.add_command(label='Save to file…', command=self._save_output_to_file)
        menu.add_separator()
        menu.add_command(label='Clear',
                         command=lambda: self.output_text.delete('1.0', tk.END))

        def show(event):
            # Enable Copy only when there's a selection; Copy all / Save / Clear
            # only when the widget has content.
            try:
                self.output_text.selection_get()
                menu.entryconfig('Copy', state=tk.NORMAL)
            except tk.TclError:
                menu.entryconfig('Copy', state=tk.DISABLED)
            has_content = bool(self.output_text.get('1.0', 'end-1c'))
            for label in ('Copy all', 'Save to file…', 'Clear'):
                menu.entryconfig(label, state=tk.NORMAL if has_content else tk.DISABLED)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        self.output_text.bind('<Button-3>', show)

    def _copy_output_selection(self):
        try:
            text = self.output_text.selection_get()
        except tk.TclError:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _copy_output_all(self):
        text = self.output_text.get('1.0', 'end-1c')
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _save_output_to_file(self):
        text = self.output_text.get('1.0', 'end-1c')
        if not text:
            return
        path = filedialog.asksaveasfilename(
            title='Save output to file',
            defaultextension='.log',
            filetypes=[('Log files', '*.log'),
                       ('Text files', '*.txt'),
                       ('All files', '*.*')],
            parent=self.root,
        )
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
        except OSError as e:
            messagebox.showerror('Save output', str(e))

    def _stream_to_output(self, process):
        self._current_process = process
        try:
            for line in iter(process.stdout.readline, ''):
                clean = strip_ansi(line)
                self.root.after(0, self.append_output, clean)
                self._detect_progress(clean)
            process.stdout.close()
            return process.wait()
        finally:
            self._current_process = None

    def _stop_current(self):
        """Terminate the running subprocess tree.

        PowerShell on Windows spawns child processes for downloads/extraction;
        `taskkill /T /F` kills the whole tree so an in-progress install
        actually stops instead of orphaning its workers.
        """
        proc = self._current_process
        if proc is None:
            return
        self.append_output('\n^C (stopping…)\n')
        try:
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                creationflags=subprocess.CREATE_NO_WINDOW,
                check=False, capture_output=True, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    def _detect_progress(self, line):
        """Update the progress phase label from `:: [Phase] ::` markers."""
        m = _PHASE_RE.search(line)
        if not m:
            return
        phase = m.group(1).strip()
        # [Info] is the high-frequency housekeeping tag; ignore so the label
        # doesn't flicker. Keep the rest verbatim.
        if phase.lower() != 'info':
            self.root.after(0, self.progress_phase_var.set, phase + '…')

    def _set_busy(self, busy):
        state = tk.DISABLED if busy else tk.NORMAL
        for w in (self.install_button, self.uninstall_button, self.run_button,
                  self.refresh_button, self.refresh_status_button,
                  self.fix_path_button, self.open_root_button, self.browse_button,
                  *self.quick_buttons, *self.install_latest_buttons):
            w.config(state=state)
        self.status_var.set('Running…' if busy else 'Idle')
        if busy:
            self.progress_phase_var.set('')
            self.progress_frame.grid()
            self.progress_bar.start(15)
        else:
            self.progress_bar.stop()
            self.progress_frame.grid_remove()

    def _with_busy(self, task):
        if self.is_busy:
            return
        self.is_busy = True
        self._set_busy(True)

        def worker():
            try:
                task()
            except Exception as e:
                self.root.after(0, self.append_output, f'Error: {e}\n')
            finally:
                self.is_busy = False
                self.root.after(0, self._set_busy, False)
                # State may have changed (install/uninstall/global/local/shell);
                # refresh the status panel after every command.
                self.root.after(0, self.refresh_status)

        threading.Thread(target=worker, daemon=True).start()

    def run_external(self, label, command_str, on_complete=None):
        """Run an arbitrary PowerShell command, streaming to the Output pane."""
        def task():
            self.root.after(0, self.append_output, f'> {label}\n')
            proc = run_powershell(command_str)
            self._stream_to_output(proc)
            if on_complete:
                self.root.after(0, on_complete)
        self._with_busy(task)

    def _rebuild_install_latest_buttons(self):
        """Rebuild the per-series 'Python X.Y (X.Y.Z)' buttons from the cache."""
        for btn in self.install_latest_buttons:
            btn.destroy()
        self.install_latest_buttons.clear()

        installable = self.versions_cache.get('installable')
        if installable is None:
            self.install_latest_label.config(text='Loading installable versions…')
            return
        if not installable:
            self.install_latest_label.config(
                text='(no installable versions — is pyenv-win installed?)',
            )
            return

        self.install_latest_label.config(text='Latest stable:')
        for s in pyenv_mod.extract_series(installable)[:4]:
            latest = pyenv_mod.latest_in_series(installable, s)
            if not latest:
                continue
            btn = tk.Button(
                self.install_python_frame,
                text=f'Python {s} ({latest})',
                command=lambda v=latest: self._install_latest_confirmed(v),
            )
            # New side=LEFT packs go to the right of existing LEFT widgets
            # (the label), and side=RIGHT widgets (Browse) keep their slot at
            # the right edge. Final order: label | series buttons | … | Browse.
            btn.pack(side=tk.LEFT, padx=2, pady=6)
            if self.is_busy:
                btn.config(state=tk.DISABLED)
            self.install_latest_buttons.append(btn)

    def _install_latest_confirmed(self, version):
        if not messagebox.askyesno(
            'Install Python',
            f'Install Python {version}?\n\n'
            f'This downloads and installs from the official mirror and may take '
            f'a few minutes.',
        ):
            return
        self.run_pyenv_subcommand('install', version)

    def run_pyenv_subcommand(self, key, args=''):
        cmdline = f'pyenv {key} {args}'.strip()

        def task():
            self.root.after(0, self.append_output, f'> {cmdline}\n')
            proc = run_powershell(cmdline)
            self._stream_to_output(proc)
            if key in ('install', 'uninstall', 'duplicate'):
                self.versions_cache['installed'] = None
                self.query_versions(
                    'installed',
                    lambda v: self._apply_versions_to_arg('installed', v),
                    silent=True,
                )

        self._with_busy(task)

    # ----- Status panel -----------------------------------------------

    def _show_path_warning(self, msg):
        self.path_warning_var.set(f'⚠ {msg}')
        self.path_row.grid()

    def _hide_path_warning(self):
        self.path_warning_var.set('')
        self.path_row.grid_remove()

    @staticmethod
    def _format_scope_value(output, returncode):
        if returncode != 0:
            return '(not set)'
        line = first_version_line(output)
        if not line:
            return '(not set)'
        return line.split()[0]

    def refresh_status(self):
        """Re-query pyenv for active/global/local/shell and refresh PATH warning."""
        def task():
            # Kick off all four queries in parallel — Popen is non-blocking;
            # communicate() then collects all of them.
            procs = {
                'active': run_powershell('pyenv version', stream=False),
                'global': run_powershell('pyenv global', stream=False),
                'local':  run_powershell('pyenv local', stream=False),
                'shell':  run_powershell('pyenv shell', stream=False),
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
                active = '(no activated pyenv-win version detected)'
            else:
                active = first_version_line(out_a) or '(no Python version detected)'
            self.root.after(0, self.active_var.set, f'Active: {active}')

            rc, out = results['global']
            self.root.after(0, self.global_var.set,
                            f'Global: {self._format_scope_value(out, rc)}')

            rc, out = results['local']
            self.root.after(0, self.local_var.set,
                            f'Local: {self._format_scope_value(out, rc)}')

            rc, out = results['shell']
            self.root.after(0, self.shell_var.set,
                            f'Shell: {self._format_scope_value(out, rc)}')

            ok, msg = pyenv_mod.check_pyenv_path()
            if not ok and rc_a != 0:
                self.root.after(
                    0, self._show_path_warning,
                    'pyenv-win is not installed or not on PATH. '
                    'Use "Install / Update pyenv-win" below.',
                )
            elif not ok:
                self.root.after(0, self._show_path_warning, msg)
            else:
                self.root.after(0, self._hide_path_warning)

        threading.Thread(target=task, daemon=True).start()

    def current_active_version(self):
        """Extract just the version string from the active_var banner text."""
        text = self.active_var.get()
        if not text.startswith('Active: '):
            return None
        rest = text[len('Active: '):].strip()
        if not rest:
            return None
        first = rest.split()[0]
        return first if first and first[0].isdigit() else None

    # ----- Version querying -------------------------------------------

    def query_versions(self, kind, on_done, silent=False):
        cmd = 'pyenv versions' if kind == 'installed' else 'pyenv install -l'

        def task():
            try:
                proc = run_powershell(cmd, stream=False)
                out, _ = proc.communicate()
            except FileNotFoundError:
                self.root.after(0, on_done, [])
                return
            if proc.returncode != 0:
                if not silent:
                    self.root.after(0, self.append_output,
                                    f'Failed to load {kind} versions.\n')
                self.root.after(0, on_done, [])
                return
            versions = pyenv_mod.parse_versions(out)
            self.versions_cache[kind] = versions
            self.root.after(0, on_done, versions)

        threading.Thread(target=task, daemon=True).start()

    def _apply_versions_to_arg(self, kind, versions):
        """Only update the args combobox if the current command actually wants this list."""
        key = self._current_command_key()
        if not key:
            return
        if pyenv_mod.COMMANDS[key].get('source') == kind:
            self.arg_entry.config(values=versions)

    def _refresh_versions(self):
        key = self._current_command_key()
        if not key:
            return
        source = pyenv_mod.COMMANDS[key].get('source')
        if not source:
            return
        self.versions_cache[source] = None
        self.append_output(f'Refreshing {source} versions…\n')
        self.query_versions(source, lambda v: self._apply_versions_to_arg(source, v))

    # ----- Command form -----------------------------------------------

    def _current_command_key(self):
        return pyenv_mod.LABEL_TO_KEY.get(self.command_var.get(), '')

    def _on_command_changed(self, *_):
        key = self._current_command_key()
        if not key:
            return
        meta = pyenv_mod.COMMANDS[key]
        self.help_var.set(meta['help'])
        self.arg_var.set('')

        if meta['arg'] is None:
            self.arg_label.config(text='(no arguments)')
            self.arg_entry.config(state='disabled', values=())
            self.refresh_button.grid_remove()
        elif meta['arg'] == 'version':
            self.arg_label.config(text='Version:')
            self.arg_entry.config(state='normal')
            source = meta['source']
            cached = self.versions_cache[source]
            if cached is not None:
                self.arg_entry.config(values=cached)
            else:
                self.arg_entry.config(values=())
                self.query_versions(source,
                                    lambda v: self._apply_versions_to_arg(source, v))
            self.refresh_button.grid()
        elif meta['arg'] == 'command':
            self.arg_label.config(text='Command:')
            self.arg_entry.config(state='normal', values=())
            self.refresh_button.grid_remove()

    def _run_command(self):
        key = self._current_command_key()
        if not key:
            return
        meta = pyenv_mod.COMMANDS[key]
        args = self.arg_var.get().strip() if meta['arg'] else ''
        if meta['arg'] and not args:
            self.append_output(f'Provide a {meta["arg"]} for "{meta["label"]}".\n')
            return
        self.run_pyenv_subcommand(key, args)

    # ----- pyenv-win install/uninstall --------------------------------

    def _run_bundled_installer(self, uninstall=False):
        """Run the vendored install-pyenv-win.ps1, extracted from the package.

        `as_file` returns a real on-disk path even when running from a
        PyInstaller --onefile build (where package resources are extracted to
        a temp dir at runtime). The context manager cleans up on exit.
        """
        suffix = ' -Uninstall' if uninstall else ''
        with as_file(files('pyenv_gui').joinpath(pyenv_mod.INSTALL_SCRIPT_NAME)) as ps1:
            proc = run_powershell(f'& "{ps1}"{suffix}')
            self._stream_to_output(proc)

    def _install_update(self):
        def task():
            if pyenv_mod.pyenv_installed():
                self.root.after(
                    0, self.append_output,
                    'pyenv-win is already installed; running installer will update it.\n',
                )
            self.root.after(0, self.append_output, 'Starting installation…\n')
            self._run_bundled_installer(uninstall=False)
        self._with_busy(task)

    def _uninstall_pyenv(self):
        def task():
            if not pyenv_mod.pyenv_installed():
                self.root.after(
                    0, self.append_output,
                    'pyenv-win is not installed, nothing to uninstall.\n',
                )
                return
            self.root.after(0, self.append_output, 'Starting uninstallation…\n')
            self._run_bundled_installer(uninstall=True)
        self._with_busy(task)

    def _open_pyenv_root(self):
        p = pyenv_mod.get_pyenv_root()
        if not p:
            messagebox.showerror(
                'Open pyenv root',
                'Could not find the pyenv-win installation directory.'
            )
            return
        try:
            os.startfile(p)
        except OSError as e:
            messagebox.showerror('Open pyenv root', str(e))

    def _fix_path(self):
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
            self.root.after(0, self.append_output, '> Fix pyenv-win PATH (USER scope)\n')
            proc = run_powershell(pyenv_mod.FIX_PATH_PS)
            rc = self._stream_to_output(proc)
            # Update this process's own PATH so any subsequent pyenv calls from
            # this GUI session see the new shims.
            if rc == 0:
                new_path = pyenv_mod.persistent_path()
                if new_path:
                    os.environ['PATH'] = new_path

        self._with_busy(task)
