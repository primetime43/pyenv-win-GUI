"""pyenv-win GUI package. Entry point is `main()`."""

__version__ = '2.0.0'


def main():
    from .app import App
    App().run()
