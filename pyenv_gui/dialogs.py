"""Toplevel dialogs: Manage installed, Create venv, pip panel.

Dialogs are functions (not classes) that take the App instance as their first
parameter. They use app.root for parenting, app.run_external /
app.run_pyenv_subcommand for operations, and app.is_busy as a re-entry guard.
"""

import json
import os
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import pyenv as pyenv_mod
from .shell import run_powershell, strip_ansi


def _query_pip_list(app, exe, on_done):
    """Run `<exe> -m pip list --format=json` in a thread; on_done(list|None) on main thread."""
    cmd = f'& "{exe}" -m pip list --format=json'

    def task():
        try:
            proc = run_powershell(cmd, stream=False)
            out, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            app.root.after(0, on_done, None)
            return
        except FileNotFoundError:
            app.root.after(0, on_done, None)
            return
        if proc.returncode != 0:
            app.root.after(0, on_done, None)
            return
        try:
            data = json.loads(strip_ansi(out))
        except json.JSONDecodeError:
            app.root.after(0, on_done, None)
            return
        app.root.after(0, on_done, data if isinstance(data, list) else None)

    threading.Thread(target=task, daemon=True).start()


def open_venv_dialog(app, version, exe):
    """Pick a folder, run `<exe> -m venv <folder>`."""
    dialog = tk.Toplevel(app.root)
    dialog.title(f'Create venv — Python {version}')
    dialog.geometry('580x190')
    dialog.transient(app.root)
    dialog.columnconfigure(1, weight=1)

    ttk.Label(dialog, text='Python:').grid(row=0, column=0, sticky='w', padx=10, pady=(10, 4))
    ttk.Label(dialog, text=exe, foreground='#555').grid(
        row=0, column=1, columnspan=2, sticky='w', pady=(10, 4), padx=(0, 10))

    ttk.Label(dialog, text='Target folder:').grid(row=1, column=0, sticky='w', padx=10, pady=4)
    target_var = tk.StringVar(value=os.path.join(os.getcwd(), '.venv'))
    target_entry = ttk.Entry(dialog, textvariable=target_var)
    target_entry.grid(row=1, column=1, sticky='ew', padx=4, pady=4)

    def browse():
        d = filedialog.askdirectory(title='Choose folder for venv', parent=dialog)
        if d:
            target_var.set(d)

    tk.Button(dialog, text='Browse…', command=browse).grid(row=1, column=2, padx=(0, 10), pady=4)

    ttk.Label(dialog,
              text='The venv will be created at this exact path (e.g., ...\\myproj\\.venv).',
              foreground='#888').grid(row=2, column=1, columnspan=2,
                                      sticky='w', padx=4, pady=(0, 8))

    def create():
        target = target_var.get().strip().strip('"')
        if not target:
            messagebox.showerror('Create venv', 'Choose a target folder.', parent=dialog)
            return
        if os.path.isdir(target) and os.listdir(target):
            if not messagebox.askyesno(
                'Folder not empty',
                f'{target}\n\nalready exists and is not empty. Create venv anyway?',
                parent=dialog,
            ):
                return
        dialog.destroy()

        activate_ps1 = os.path.join(target, 'Scripts', 'Activate.ps1')

        def hint():
            app.append_output(
                f'\nVenv ready at:\n  {target}\n'
                f'To activate in PowerShell:\n  & "{activate_ps1}"\n'
            )
        app.run_external(
            f'python -m venv "{target}"',
            f'& "{exe}" -m venv "{target}"',
            on_complete=hint,
        )

    btn_frame = tk.Frame(dialog)
    btn_frame.grid(row=3, column=0, columnspan=3, sticky='ew', padx=10, pady=10)
    btn_frame.columnconfigure(0, weight=1)
    tk.Button(btn_frame, text='Create venv', command=create).grid(row=0, column=1, padx=(0, 4))
    tk.Button(btn_frame, text='Cancel', command=dialog.destroy).grid(row=0, column=2)

    target_entry.focus_set()
    target_entry.icursor(tk.END)


def open_pip_dialog(app, version, exe):
    """Per-version pip panel: list, install, freeze, uninstall."""
    dialog = tk.Toplevel(app.root)
    dialog.title(f'pip — Python {version}')
    dialog.geometry('620x520')
    dialog.minsize(500, 360)
    dialog.transient(app.root)
    dialog.columnconfigure(0, weight=1)
    dialog.rowconfigure(2, weight=1)

    install_frame = tk.Frame(dialog)
    install_frame.grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 4))
    install_frame.columnconfigure(1, weight=1)

    ttk.Label(install_frame, text='Install package:').grid(row=0, column=0, sticky='w', padx=(0, 6))
    pkg_var = tk.StringVar()
    pkg_entry = ttk.Entry(install_frame, textvariable=pkg_var)
    pkg_entry.grid(row=0, column=1, sticky='ew')
    install_btn = tk.Button(install_frame, text='Install')
    install_btn.grid(row=0, column=2, padx=(6, 0))

    status_var_pip = tk.StringVar(value='Loading packages…')
    ttk.Label(dialog, textvariable=status_var_pip,
              foreground='#555').grid(row=1, column=0, sticky='w', padx=10)

    tree_frame = tk.Frame(dialog)
    tree_frame.grid(row=2, column=0, sticky='nsew', padx=10, pady=4)
    tree_frame.rowconfigure(0, weight=1)
    tree_frame.columnconfigure(0, weight=1)

    tree = ttk.Treeview(tree_frame, columns=('package', 'version'),
                        show='headings', selectmode='browse')
    tree.heading('package', text='Package')
    tree.heading('version', text='Version')
    tree.column('package', width=320, anchor='w')
    tree.column('version', width=140, anchor='w')
    tree.grid(row=0, column=0, sticky='nsew')

    scroll = tk.Scrollbar(tree_frame, command=tree.yview)
    scroll.grid(row=0, column=1, sticky='ns')
    tree['yscrollcommand'] = scroll.set

    btn_frame = tk.Frame(dialog)
    btn_frame.grid(row=3, column=0, sticky='ew', padx=10, pady=10)
    btn_frame.columnconfigure(0, weight=1)

    def load_packages():
        status_var_pip.set('Loading packages…')
        tree.delete(*tree.get_children())

        def on_done(packages):
            if packages is None:
                status_var_pip.set(
                    'Failed to load packages — pip may not be installed for this version.'
                )
                return
            for p in packages:
                tree.insert('', tk.END,
                            values=(p.get('name', ''), p.get('version', '')))
            n = len(packages)
            status_var_pip.set(f'{n} package{"s" if n != 1 else ""}')

        _query_pip_list(app, exe, on_done)

    def do_install():
        pkg = pkg_var.get().strip()
        if not pkg or app.is_busy:
            return
        pkg_var.set('')
        app.run_external(
            f'pip install {pkg}',
            f'& "{exe}" -m pip install {pkg}',
            on_complete=load_packages,
        )

    install_btn.config(command=do_install)
    pkg_entry.bind('<Return>', lambda _e: do_install())

    def do_freeze():
        if app.is_busy:
            return
        app.run_external('pip freeze', f'& "{exe}" -m pip freeze')

    def do_uninstall():
        if app.is_busy:
            return
        sel = tree.selection()
        if not sel:
            return
        pkg = tree.set(sel[0], 'package')
        if not pkg:
            return
        if not messagebox.askyesno(
            'Uninstall package',
            f'Uninstall {pkg} from Python {version}?',
            parent=dialog,
        ):
            return
        app.run_external(
            f'pip uninstall -y {pkg}',
            f'& "{exe}" -m pip uninstall -y {pkg}',
            on_complete=load_packages,
        )

    tk.Button(btn_frame, text='Refresh', command=load_packages).grid(row=0, column=1, padx=(0, 4))
    tk.Button(btn_frame, text='pip freeze → output', command=do_freeze).grid(row=0, column=2, padx=(0, 4))
    tk.Button(btn_frame, text='Uninstall selected…', command=do_uninstall).grid(row=0, column=3, padx=(0, 4))
    tk.Button(btn_frame, text='Close', command=dialog.destroy).grid(row=0, column=4)

    load_packages()


def open_manage_dialog(app):
    """Show a Treeview of installed Python versions with right-click actions."""
    pyenv_root = pyenv_mod.get_pyenv_root()
    versions_dir = os.path.join(pyenv_root, 'versions') if pyenv_root else None
    if not versions_dir or not os.path.isdir(versions_dir):
        messagebox.showerror(
            'pyenv-win not found',
            'Could not find the pyenv versions directory.\n'
            'Install pyenv-win first using "Install / Update pyenv-win".'
        )
        return

    dialog = tk.Toplevel(app.root)
    dialog.title('Manage installed Python versions')
    dialog.geometry('820x460')
    dialog.minsize(640, 320)
    dialog.transient(app.root)
    dialog.columnconfigure(0, weight=1)
    dialog.rowconfigure(0, weight=1)

    tree_frame = tk.Frame(dialog)
    tree_frame.grid(row=0, column=0, sticky='nsew', padx=10, pady=(10, 5))
    tree_frame.rowconfigure(0, weight=1)
    tree_frame.columnconfigure(0, weight=1)

    columns = ('active', 'version', 'exe', 'size')
    tree = ttk.Treeview(tree_frame, columns=columns, show='headings', selectmode='browse')
    tree.heading('active', text='Active')
    tree.heading('version', text='Version')
    tree.heading('exe', text='Executable')
    tree.heading('size', text='Size')
    tree.column('active', width=60, anchor='center', stretch=False)
    tree.column('version', width=110, anchor='w', stretch=False)
    tree.column('exe', width=440, anchor='w')
    tree.column('size', width=90, anchor='e', stretch=False)
    tree.grid(row=0, column=0, sticky='nsew')

    tree.tag_configure('active', background='#fff9e6',
                       font=('TkDefaultFont', 9, 'bold'))

    scroll = tk.Scrollbar(tree_frame, command=tree.yview)
    scroll.grid(row=0, column=1, sticky='ns')
    tree['yscrollcommand'] = scroll.set

    info_frame = tk.Frame(dialog)
    info_frame.grid(row=1, column=0, sticky='ew', padx=10, pady=(0, 2))
    info_frame.columnconfigure(0, weight=1)
    total_var = tk.StringVar(value='Total: calculating…')
    status_msg_var = tk.StringVar(value='')
    ttk.Label(info_frame, textvariable=total_var).grid(row=0, column=0, sticky='w')
    ttk.Label(info_frame, textvariable=status_msg_var,
              foreground='#888').grid(row=0, column=1, sticky='e')

    button_frame = tk.Frame(dialog)
    button_frame.grid(row=2, column=0, sticky='ew', padx=10, pady=10)
    button_frame.columnconfigure(0, weight=1)
    ttk.Label(button_frame, text='Right-click a row for actions.',
              foreground='#666').grid(row=0, column=0, sticky='w')

    def selected_version():
        sel = tree.selection()
        return tree.set(sel[0], 'version') if sel else None

    def flash_status(msg):
        status_msg_var.set(msg)
        dialog.after(2500, lambda: status_msg_var.set(''))

    def open_folder():
        v = selected_version()
        if not v:
            return
        path = os.path.join(versions_dir, v)
        try:
            os.startfile(path)
            flash_status(f'Opened {path}')
        except OSError as e:
            messagebox.showerror('Open folder', str(e))

    def copy_path():
        v = selected_version()
        if not v:
            return
        path = os.path.join(versions_dir, v, 'python.exe')
        dialog.clipboard_clear()
        dialog.clipboard_append(path)
        flash_status('Path copied to clipboard')

    def set_global():
        v = selected_version()
        if not v:
            return
        dialog.destroy()
        app.run_pyenv_subcommand('global', v)

    def uninstall_version():
        v = selected_version()
        if not v:
            return
        if not messagebox.askyesno(
            'Uninstall Python',
            f'Uninstall Python {v}?\n\n'
            f'This will delete:\n  {os.path.join(versions_dir, v)}\n\n'
            f'This cannot be undone.'
        ):
            return
        dialog.destroy()
        app.run_pyenv_subcommand('uninstall', v)

    def create_venv():
        v = selected_version()
        if not v:
            return
        open_venv_dialog(app, v, os.path.join(versions_dir, v, 'python.exe'))

    def manage_pip():
        v = selected_version()
        if not v:
            return
        open_pip_dialog(app, v, os.path.join(versions_dir, v, 'python.exe'))

    context_menu = tk.Menu(dialog, tearoff=0)
    context_menu.add_command(label='Set as Global', command=set_global)
    context_menu.add_separator()
    context_menu.add_command(label='Create venv…', command=create_venv)
    context_menu.add_command(label='Manage packages (pip)…', command=manage_pip)
    context_menu.add_separator()
    context_menu.add_command(label='Uninstall…', command=uninstall_version)
    context_menu.add_separator()
    context_menu.add_command(label='Open Folder', command=open_folder)
    context_menu.add_command(label='Copy Path', command=copy_path)

    def show_context_menu(event):
        iid = tree.identify_row(event.y)
        if not iid:
            return
        tree.selection_set(iid)
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    tree.bind('<Button-3>', show_context_menu)

    def load():
        tree.delete(*tree.get_children())
        total_var.set('Total: calculating…')
        try:
            versions = sorted(
                [d for d in os.listdir(versions_dir)
                 if os.path.isdir(os.path.join(versions_dir, d))],
                key=lambda v: tuple(int(p) if p.isdigit() else 0
                                    for p in v.split('.')),
                reverse=True,
            )
        except OSError as e:
            messagebox.showerror('Read versions', str(e))
            return

        if not versions:
            total_var.set('No Python versions installed.')
            return

        active_now = app.current_active_version()
        item_ids = {}
        for v in versions:
            exe = os.path.join(versions_dir, v, 'python.exe')
            is_active = (v == active_now)
            tags = ('active',) if is_active else ()
            iid = tree.insert(
                '', tk.END,
                values=('★' if is_active else '', v, exe, '…'),
                tags=tags,
            )
            item_ids[v] = iid

        # Compute disk sizes on a background thread.
        def compute_sizes():
            total = 0
            for v in versions:
                size = pyenv_mod.dir_size(os.path.join(versions_dir, v))
                total += size
                app.root.after(
                    0,
                    lambda i=item_ids[v], s=pyenv_mod.format_size(size):
                        tree.set(i, 'size', s),
                )
            app.root.after(
                0,
                lambda t=total: total_var.set(f'Total: {pyenv_mod.format_size(t)}'),
            )

        threading.Thread(target=compute_sizes, daemon=True).start()

    tk.Button(button_frame, text='Refresh', command=load).grid(row=0, column=1, padx=(0, 4))
    tk.Button(button_frame, text='Close', command=dialog.destroy).grid(row=0, column=2)

    load()
