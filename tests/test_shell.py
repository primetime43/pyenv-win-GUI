from pyenv_gui.shell import first_version_line, strip_ansi


def test_strip_ansi_removes_sgr_codes():
    assert strip_ansi('\x1b[91mFATAL\x1b[0m: oops') == 'FATAL: oops'


def test_strip_ansi_handles_complex_codes():
    assert strip_ansi('\x1b[1;31;47mbold red\x1b[0m') == 'bold red'


def test_strip_ansi_preserves_plain_text():
    assert strip_ansi('hello world\n') == 'hello world\n'


def test_first_version_line_walks_past_warnings():
    text = (
        '\x1b[91mFATAL: Found python.exe before pyenv in PATH\x1b[0m\n'
        '3.12.0 (set by C:\\.python-version)\n'
    )
    assert first_version_line(text) == '3.12.0 (set by C:\\.python-version)'


def test_first_version_line_returns_empty_when_no_version():
    assert first_version_line('FATAL: nothing here\nwarning: still nothing') == ''


def test_first_version_line_handles_empty_input():
    assert first_version_line('') == ''
