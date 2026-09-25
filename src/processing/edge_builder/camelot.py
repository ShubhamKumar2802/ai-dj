def _parse_camelot(key: str | None) -> tuple[int, str] | None:
    if key is None or len(key) < 2:
        return None

    letter = key[-1].upper()
    number_part = key[:-1]
    if letter not in ("A", "B") or not number_part.isdigit():
        return None

    number = int(number_part)
    if not 1 <= number <= 12:
        return None

    return number, letter


def wheel_distance(n_a: int, n_b: int) -> int:
    diff = abs(n_a - n_b)
    return min(diff, 12 - diff)


def reachable_keys(key: str | None) -> set[str]:
    """The domain doc's (resources/ai-dj-domain-and-architecture.md §1.1) three
    free moves from `key`, plus `key` itself: same key; +-1, same letter
    (perfect fifth); same number, flip letter (relative major/minor). Empty
    set if `key` is None or unparseable — such a track can never appear in a
    Camelot-adjacency-only chain (experiments/llm_camelot_sequencer — the one
    caller that treats key as a hard gate rather than the soft key_distance
    cost every other consumer of this module uses)."""
    parsed = _parse_camelot(key)
    if parsed is None:
        return set()
    number, letter = parsed
    other_letter = "A" if letter == "B" else "B"

    def _wrap(n: int) -> int:
        return ((n - 1) % 12) + 1

    return {
        f"{number}{letter}",
        f"{_wrap(number - 1)}{letter}",
        f"{_wrap(number + 1)}{letter}",
        f"{number}{other_letter}",
    }


def key_distance(key_a: str | None, key_b: str | None) -> float:
    parsed_a = _parse_camelot(key_a)
    parsed_b = _parse_camelot(key_b)
    if parsed_a is None or parsed_b is None:
        return 0.5

    number_a, letter_a = parsed_a
    number_b, letter_b = parsed_b
    distance = wheel_distance(number_a, number_b)
    same_letter = letter_a == letter_b

    if distance == 0 and same_letter:
        return 0.00
    if distance == 1 and same_letter:
        return 0.25
    if distance == 0 and not same_letter:
        return 0.25
    if distance == 1 and not same_letter:
        return 1.00
    return min(1.0, distance / 6.0)
