"""Synthetic LyricLine / Transcript builders shared by the lyrics_sourcing tests."""

from experiments.lyrics_sourcing.schema import LyricLine, Segment, Transcript, Word

# Hindi-ish romanized lyric lines; the chorus line repeats (as real songs do).
CHORUS = "abhi toh party shuru hui hai"
LYRIC_TEXTS = [
    "yeh raat hai deewani mastani",
    "dil mera dhadke tere liye",
    CHORUS,
    "naach le tu saari raat",
    "chal chalein hum door kahin",
    "sapne saare sach honge",
    CHORUS,
    "koi rok na paaye humko",
    "aaj hai apna din yaaro",
    CHORUS,
]


def lyric_lines(starts: list[float] | None = None, texts: list[str] | None = None):
    texts = texts or LYRIC_TEXTS
    starts = starts or [10.0 + 8.0 * i for i in range(len(texts))]
    return [
        LyricLine(start=s, end=starts[i + 1] if i + 1 < len(starts) else None, text=t)
        for i, (s, t) in enumerate(zip(starts, texts))
    ]


def transcript_from(lines, shift: float = 0.0, word_s: float = 0.4) -> Transcript:
    """A transcript that 'hears' every line `shift` seconds later than the lyrics say."""
    segments = []
    for line in lines:
        start = line.start + shift
        words = [
            Word(text=w, start=start + j * word_s, end=start + (j + 1) * word_s, probability=0.9)
            for j, w in enumerate(line.text.split())
        ]
        segments.append(Segment(text=line.text, start=start, end=words[-1].end, words=words))
    return Transcript(language="hi", segments=segments, whisper_config_id="test", model="test")
