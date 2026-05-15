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
- **Progress bar with phase label and Stop button** during long-running operations. Stop force-terminates the whole subprocess tree, not just the parent shell.
- **Hover tooltips** on every button explaining what they do.
- **Persistent settings** — window size and last selected command are saved to `%APPDATA%\pyenv-win-GUI\settings.json`.

## Requirements



## Download

Grab the latest standalone `.exe` from the [Releases page](https://github.com/primetime43/pyenv-win-GUI/releases) — no Python install required.

## Screenshots

<img width="722" height="752" alt="image" src="https://github.com/user-attachments/assets/9d1e104c-3bdb-4f36-a603-e9a9cb9dbe33" />

*Main window — install / manage versions, run pyenv commands, see what's active.*

<img width="822" height="492" alt="image" src="https://github.com/user-attachments/assets/e5e003f4-9fa7-4280-8937-ef49e82a7137" />

*Manage installed dialog — per-version disk usage and active marker; right-click for set-global, uninstall, venv, or pip.*

<img width="722" height="572" alt="image" src="https://github.com/user-attachments/assets/fda64cdc-5f6e-41fa-bfcd-cd4dc035e06d" />

*Browse installable dialog — filter by major version, search, install with one click.*

<img width="622" height="552" alt="image" src="https://github.com/user-attachments/assets/9a6166b3-c794-45b3-8813-2b61960ae1d9" />

*pip panel — list, install, freeze, uninstall packages for the selected Python version.*

<details>
<summary>Older screenshots (earlier UI layout)</summary>

![image](https://github.com/primetime43/pyenv-win-GUI/assets/12754111/c6a77800-b388-4861-b891-7489a4300745)

![image](https://github.com/primetime43/pyenv-win-GUI/assets/12754111/eea5983b-7d43-4b3d-b021-b542175fb70b)

![image](https://github.com/primetime43/pyenv-win-GUI/assets/12754111/bddd0a38-57ef-4e16-94ac-67e17588c434)

</details>
