from experiments.lyrics_sourcing.steps.lyrics.lrc import parse_lrc


def test_basic_lines_chain_ends():
    lines = parse_lrc("[00:12.00] first\n[00:15.50] second\n")
    assert [(ln.start, ln.end, ln.text) for ln in lines] == [
        (12.0, 15.5, "first"),
        (15.5, None, "second"),
    ]


def test_multi_timestamp_line_expands_and_sorts():
    lines = parse_lrc("[00:12.00][01:30.00] chorus\n[00:20.00] verse\n")
    assert [(ln.start, ln.text) for ln in lines] == [
        (12.0, "chorus"),
        (20.0, "verse"),
        (90.0, "chorus"),
    ]


def test_positive_offset_makes_lyrics_earlier():
    lines = parse_lrc("[offset:+500]\n[00:10.00] a\n")
    assert lines[0].start == 9.5


def test_metadata_tags_and_empty_lines_dropped():
    text = "[ar:Artist]\n[ti:Title]\n[length: 03:20]\n\n[00:05.00]\n[00:06.00] real\n"
    lines = parse_lrc(text)
    assert [(ln.start, ln.text) for ln in lines] == [(6.0, "real")]


def test_three_digit_fraction():
    assert parse_lrc("[01:02.345] x")[0].start == 62.345
