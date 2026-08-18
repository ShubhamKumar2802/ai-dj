from ingestion.cue_derivation.config import CueDerivationConfig
from ingestion.cue_derivation.cues import emit_cues
from ingestion.cue_derivation.grid_origin import derive_grid_origin
from ingestion.cue_derivation.hook import detect_hook
from ingestion.cue_derivation.phrase_grid import detect_phrase_boundaries
from ingestion.cue_derivation.schema import CueDerivationResult
from ingestion.cue_derivation.status import quarantine
from ingestion.cue_derivation.structure_template import classify_structure_template
from ingestion.feature_extractor.schema import RawFeatures


def derive_cues(raw: RawFeatures, config: CueDerivationConfig) -> CueDerivationResult:
    """Spec §9's orchestrator — literal translation of its numbered steps.
    No cache layer (unlike feature_extractor's extract.py) — this module is
    the cheap, volatile half of D6's split precisely so it doesn't need one.
    """
    grid_start, grid_confidence, free_intro_end = derive_grid_origin(raw)
    phrase_grid, phrase_length_bars = detect_phrase_boundaries(raw, config)
    structure_template = classify_structure_template(raw, free_intro_end, phrase_grid, config)
    hook_in, hook_exit = detect_hook(raw, phrase_grid, config)
    cue_ins, cue_outs = emit_cues(
        raw,
        grid_start,
        free_intro_end,
        structure_template,
        hook_in,
        hook_exit,
        phrase_grid,
        config,
    )
    status = quarantine(grid_confidence, config)

    return CueDerivationResult(
        grid_start=grid_start,
        grid_confidence=grid_confidence,
        free_intro_end=free_intro_end,
        phrase_length_bars=phrase_length_bars,
        phrase_grid=phrase_grid,
        structure_template=structure_template,
        cue_ins=cue_ins,
        cue_outs=cue_outs,
        status=status,
        cue_derivation_version=config.cue_derivation_version,
    )
