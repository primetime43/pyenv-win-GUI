# Author: primetime43
# GitHub: https://github.com/primetime43
#
# Entry point for the pyenv-win GUI. Implementation lives in the pyenv_gui/
# package; this file exists so the README's PyInstaller command keeps working:
#     pyinstaller --onefile --noconsole "pyenv-win-GUI.py"

from pyenv_gui import main

if __name__ == '__main__':
    main()
