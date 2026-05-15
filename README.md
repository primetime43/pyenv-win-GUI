# pyenv-win-GUI

A friendly Tkinter GUI for [pyenv-win](https://github.com/pyenv-win/pyenv-win) — install, switch, and manage Python versions on Windows without memorizing pyenv commands.

## Features

- **Install / update / uninstall pyenv-win itself.** Uses the vendored official installer script — no network roundtrip on launch.
- **One-click "Install latest 3.X" buttons** plus a searchable, filterable browser of every installable version, with installed marker and "latest in series" highlight.
- **Manage installed versions** in a Treeview dialog: right-click for *Set Global / Uninstall (confirmed) / Open Folder / Copy Path*, plus per-row disk usage and active marker.
- **Per-version venv creator** (`python -m venv ...`) and **per-version pip panel** (list / install / freeze / uninstall packages).
- **Live status panel** with the active Python version banner and `global` / `local` / `shell` scopes side by side. Detects when pyenv-win's shims aren't on PATH and offers a one-click **Fix PATH** that prepends `bin` and `shims` to your USER PATH.
- **Friendly command dropdown** wrapping every pyenv subcommand with a description and version-aware argument autocompletion.
- **ANSI-clean output pane** with right-click *Copy / Copy all / Save to file… / Clear*.
- **Persistent settings** — window size and last selected command are saved to `%APPDATA%\pyenv-win-GUI\settings.json`.

## Requirements

- Windows 10/11
- Python 3.9+ (standard library only — no third-party deps)
- PowerShell (ships with Windows)

## Running

```
python pyenv-win-GUI.py
```

Or as a module:

```
python -m pyenv_gui
```

## Building a standalone .exe

```
pyinstaller --onefile --noconsole --add-data "pyenv_gui/install-pyenv-win.ps1;pyenv_gui" "pyenv-win-GUI.py"
```

The `--add-data` flag bundles the vendored pyenv-win installer script into the exe so the Install / Uninstall pyenv-win buttons keep working in the standalone build.

## Project layout

```
pyenv-win-GUI.py        Thin entry shim
pyenv_gui/
├── __init__.py         main() factory
├── shell.py            PowerShell runner, ANSI stripping, version-line walker (no Tk)
├── pyenv.py            Command metadata, version parsing, path detection, settings (no Tk)
├── dialogs.py          Manage / Browse / Venv / Pip dialogs
├── app.py              class App: main window + status panel + busy state
└── install-pyenv-win.ps1   Vendored from pyenv-win upstream
```

`shell.py` and `pyenv.py` import zero Tk and are covered by `tests/`.

## Running tests

```
pip install pytest
pytest
```

Tests cover the pure helpers (version parsing/sorting, series extraction, size formatting, ANSI stripping, …). No GUI runtime needed.

## Screenshots

> The UI has evolved since these were captured — they show an earlier version layout.

![image](https://github.com/primetime43/pyenv-win-GUI/assets/12754111/c6a77800-b388-4861-b891-7489a4300745)

![image](https://github.com/primetime43/pyenv-win-GUI/assets/12754111/eea5983b-7d43-4b3d-b021-b542175fb70b)

![image](https://github.com/primetime43/pyenv-win-GUI/assets/12754111/bddd0a38-57ef-4e16-94ac-67e17588c434)
