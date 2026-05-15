# pyenv-win-GUI

A friendly Tkinter GUI for [pyenv-win](https://github.com/pyenv-win/pyenv-win) — install, switch, and manage Python versions on Windows without memorizing pyenv commands.

## Background

[pyenv-win](https://github.com/pyenv-win/pyenv-win) is the Windows port of [pyenv](https://github.com/pyenv/pyenv) — it lets you install and switch between multiple Python versions on the same machine. It's powerful but command-line only: every operation means remembering `pyenv install 3.12.7`, `pyenv global 3.11.5`, `pyenv local 3.10.11`, `pyenv versions`, and so on. This project puts a GUI on top: install a new Python version, switch the active one, create venvs, manage pip packages per version, and see at a glance what's active and where it was set — all without typing pyenv commands.

## Features

- **Install / update / uninstall pyenv-win itself.** Uses the vendored official installer script — no network roundtrip on launch.
- **One-click "Install latest 3.X" buttons** plus a searchable, filterable browser of every installable version, with installed marker and "latest in series" highlight.
- **Manage installed versions** in a Treeview dialog: right-click for *Set Global / Uninstall (confirmed) / Open Folder / Copy Path*, plus per-row disk usage and active marker.
- **Per-version venv creator** (`python -m venv ...`) and **per-version pip panel** (list / install / freeze / uninstall packages).
- **Live status panel** with the active Python version banner and `global` / `local` / `shell` scopes side by side. Detects when pyenv-win's shims aren't on PATH and offers a one-click **Fix PATH** that prepends `bin` and `shims` to your USER PATH.
- **Friendly command dropdown** wrapping every pyenv subcommand with a description and version-aware argument autocompletion.
- **ANSI-clean output pane** with right-click *Copy / Copy all / Save to file… / Clear*.
- **Progress bar with phase label and Stop button** during long-running operations. Stop force-terminates the whole subprocess tree, not just the parent shell.
- **Hover tooltips** on every button explaining what they do.
- **Persistent settings** — window size and last selected command are saved to `%APPDATA%\pyenv-win-GUI\settings.json`.

## Requirements



## Download

Grab the latest standalone `.exe` from the [Releases page](https://github.com/primetime43/pyenv-win-GUI/releases) — no Python install required.

## Screenshots

> The UI has evolved since these were captured — they show an earlier version layout.

![image](https://github.com/primetime43/pyenv-win-GUI/assets/12754111/c6a77800-b388-4861-b891-7489a4300745)

![image](https://github.com/primetime43/pyenv-win-GUI/assets/12754111/eea5983b-7d43-4b3d-b021-b542175fb70b)

![image](https://github.com/primetime43/pyenv-win-GUI/assets/12754111/bddd0a38-57ef-4e16-94ac-67e17588c434)
