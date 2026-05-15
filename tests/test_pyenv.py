from pyenv_gui.pyenv import (
    COMMANDS,
    COMMAND_ORDER,
    LABEL_TO_KEY,
    extract_series,
    format_size,
    latest_in_series,
    parse_versions,
    sort_versions_desc,
)


def test_parse_versions_strips_active_marker_and_sorts_desc():
    text = '  3.10.11\n* 3.11.5 (set by ...)\n  3.12.0\n'
    assert parse_versions(text) == ['3.12.0', '3.11.5', '3.10.11']


def test_parse_versions_skips_info_lines():
    text = ':: [Info] :: Mirror: ...\n3.12.0\n3.11.5\n'
    assert parse_versions(text) == ['3.12.0', '3.11.5']


def test_parse_versions_handles_empty_input():
    assert parse_versions('') == []


def test_sort_versions_desc_finals_beat_prereleases_at_same_parts():
    assert sort_versions_desc(['3.12.0rc1', '3.12.0', '3.12.0a1']) == [
        '3.12.0', '3.12.0rc1', '3.12.0a1',
    ]


def test_sort_versions_desc_newer_series_first():
    assert sort_versions_desc(['3.11.5', '3.12.0', '3.10.11']) == [
        '3.12.0', '3.11.5', '3.10.11',
    ]


def test_extract_series_unique_and_sorted_desc():
    versions = ['3.11.5', '3.12.0', '3.11.4', '3.10.11', '3.12.7']
    assert extract_series(versions) == ['3.12', '3.11', '3.10']


def test_extract_series_handles_malformed_entries():
    assert extract_series(['3.12.0', 'garbage', '3.11.5']) == ['3.12', '3.11']


def test_latest_in_series_picks_highest_final():
    versions = ['3.12.0', '3.12.7', '3.12.5', '3.12.8rc1', '3.11.0']
    assert latest_in_series(versions, '3.12') == '3.12.7'


def test_latest_in_series_excludes_prereleases():
    assert latest_in_series(['3.13.0rc1', '3.13.0a2'], '3.13') is None


def test_latest_in_series_returns_none_for_unknown_series():
    assert latest_in_series(['3.12.0'], '2.7') is None


def test_format_size_units():
    assert format_size(0) == '0 B'
    assert format_size(999) == '999 B'
    assert format_size(1024) == '1.0 KB'
    assert format_size(1536) == '1.5 KB'
    assert format_size(1024 ** 2) == '1.0 MB'
    assert format_size(1024 ** 3) == '1.00 GB'


def test_command_metadata_consistency():
    # Every key in COMMAND_ORDER must exist in COMMANDS, and vice versa.
    assert set(COMMAND_ORDER) == set(COMMANDS.keys())
    # LABEL_TO_KEY must round-trip.
    for key, meta in COMMANDS.items():
        assert LABEL_TO_KEY[meta['label']] == key
    # version-arg commands must specify a source.
    for key, meta in COMMANDS.items():
        if meta['arg'] == 'version':
            assert meta.get('source') in ('installed', 'installable'), \
                f'{key} missing source'
