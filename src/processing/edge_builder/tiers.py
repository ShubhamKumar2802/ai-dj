from ingestion.orchestrator.schema import Track
from processing.edge_builder.config import EdgeBuilderConfig


def eligible_pool(tracks: list[Track]) -> list[Track]:
    return [t for t in tracks if t.status != "excluded" and len(t.downbeat_times) >= 2]


def tier2_eligible(track_a: Track, track_b: Track, config: EdgeBuilderConfig) -> bool:
    if track_a.status == "cut_only" or track_b.status == "cut_only":
        return False
    ratio = abs(track_a.bpm - track_b.bpm) / track_a.bpm
    return ratio <= config.tier2_max_bpm_ratio


def _tier_penalty_table(structure_template: str, config: EdgeBuilderConfig) -> dict[int, float]:
    if structure_template == "edm":
        return config.tier_penalties_edm
    return config.tier_penalties_film


def tier_penalty(tier: int, template_a: str, template_b: str, config: EdgeBuilderConfig) -> float:
    table_a = _tier_penalty_table(template_a, config)
    table_b = _tier_penalty_table(template_b, config)
    return (table_a[tier] + table_b[tier]) / 2.0


def eligible_tiers(track_a: Track, track_b: Track, config: EdgeBuilderConfig) -> set[int]:
    tiers = set(config.enabled_tiers)
    if 2 in tiers and not tier2_eligible(track_a, track_b, config):
        tiers.discard(2)
    return tiers
