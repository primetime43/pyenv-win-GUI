"""pyenv-win GUI package. Entry point is `main()`."""

__version__ = '2.1.0'


def main():
    from .app import App
    App().run()
