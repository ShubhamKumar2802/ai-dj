from ingestion.cue_derivation.schema import CueDerivationResult
from ingestion.feature_extractor.schema import RawFeatures
from ingestion.orchestrator.schema import Track


def _assemble_track(path: str, raw: RawFeatures, cue_result: CueDerivationResult) -> Track:
    """Pure field mapping (spec §1's table, §3) — no I/O, no exception
    handling. `path` is the caller-supplied input parameter, deliberately
    not `raw.source_path` (spec §1)."""
    return Track(
        id=raw.content_hash,
        path=path,
        content_hash=raw.content_hash,
        duration=raw.duration,
        sample_rate=raw.sample_rate,
        bpm=raw.bpm,
        bpm_confidence=raw.bpm_confidence,
        beat_times=raw.beat_times,
        downbeat_times=raw.downbeat_times,
        downbeat_confidence=raw.downbeat_confidence,
        beats_per_bar=raw.beats_per_bar,
        grid_start=cue_result.grid_start,
        grid_confidence=cue_result.grid_confidence,
        free_intro_end=cue_result.free_intro_end,
        phrase_length_bars=cue_result.phrase_length_bars,
        phrase_grid=cue_result.phrase_grid,
        key=raw.key,
        key_confidence=raw.key_confidence,
        lufs_integrated=raw.lufs_integrated,
        true_peak=raw.true_peak,
        energy_curve=raw.energy_curve,
        vocal_mask=raw.vocal_band_energy,
        structure_template=cue_result.structure_template,
        cue_ins=cue_result.cue_ins,
        cue_outs=cue_result.cue_outs,
        familiarity_score=None,
        era=None,
        is_club_edit=None,
        analysis_version=f"{raw.feature_extractor_version}+{cue_result.cue_derivation_version}",
        status=cue_result.status,
    )
