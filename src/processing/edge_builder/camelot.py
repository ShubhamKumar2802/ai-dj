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
