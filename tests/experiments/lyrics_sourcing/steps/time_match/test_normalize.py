from experiments.lyrics_sourcing.steps.time_match.normalize import (
    count_perso_arabic_words,
    normalize_text,
)


def test_punctuation_case_and_whitespace():
    assert normalize_text("  Abhi, toh PARTY!!  shuru… hui hai ") == "abhi toh party shuru hui hai"


def test_devanagari_becomes_roman():
    assert normalize_text("अभी तो पार्टी") == "abhi to parti"


def test_urdu_script_passes_through_and_is_counted():
    text = "دل دل mera"
    assert normalize_text(text) == "دل دل mera"
    assert count_perso_arabic_words(text) == 2
