from bisect import bisect_right

from ingestion.orchestrator.schema import Track


def position_to_bar(position: float, track: Track) -> int:
    bar = bisect_right(track.downbeat_times, position) - 1
    return max(0, min(bar, len(track.energy_curve) - 1))
