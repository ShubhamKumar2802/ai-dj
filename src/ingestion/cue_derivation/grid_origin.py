from ingestion.feature_extractor.schema import RawFeatures


def derive_grid_origin(raw: RawFeatures) -> tuple[float, float, float]:
    """Returns (grid_start, grid_confidence, free_intro_end) — spec §3.

    grid_start is the first *detected* downbeat, not file start (F3:
    unpulsed intros give onset detection nothing to fire on). Empty
    downbeat_times (feature_extractor's own contract: paired with
    downbeat_confidence == 0.0 whenever fewer than beats_per_bar * 2 beats
    are detected) is handled explicitly rather than indexing into an empty
    list — this is exactly the case that must flow to status="excluded"
    (§8) rather than crash before quarantine ever runs (spec §3 amendment).
    """
    if not raw.downbeat_times:
        return 0.0, raw.downbeat_confidence, 0.0

    grid_start = raw.downbeat_times[0]
    grid_confidence = raw.downbeat_confidence

    free_intro_end = grid_start
    if raw.riser_candidates and raw.riser_candidates[0].start_time < grid_start:
        free_intro_end = raw.riser_candidates[0].start_time

    return grid_start, grid_confidence, free_intro_end
