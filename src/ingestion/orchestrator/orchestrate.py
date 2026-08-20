from collections.abc import Callable
from typing import Literal

from joblib import Parallel, delayed

from common.logging import get_logger
from ingestion.orchestrator.config import IngestionConfig
from ingestion.orchestrator.schema import IngestionFailure, IngestionResult, Track
from ingestion.orchestrator.worker import _ingest_one

_logger = get_logger("ai_dj.orchestrator.orchestrate")

ProgressStatus = Literal["queued", "completed", "failed"]
OnProgress = Callable[[str, ProgressStatus], None]


def ingest_tracks(
    paths: list[str],
    config: IngestionConfig,
    on_progress: OnProgress | None = None,
    *,
    _worker: Callable[[str, IngestionConfig], Track | IngestionFailure] = _ingest_one,
    _backend: str = "loky",
) -> IngestionResult:
    """Spec §5. Dedupes paths, dispatches one _worker call per path through
    joblib's loky backend (crash-resilient process pool — see spec §6), and
    classifies each result as it arrives, not in input order.
    """
    # Order-preserving dedup by literal string equality (spec §5 step 1) —
    # catches an accidentally-repeated path for free. Does not dedupe by
    # audio content; feature_extractor's own cache (spec v3) handles that.
    deduped_paths = list(dict.fromkeys(paths))
    if len(deduped_paths) != len(paths):
        _logger.info("deduped %d repeated path(s)", len(paths) - len(deduped_paths))

    # joblib's own n_jobs=None means *sequential* (equivalent to n_jobs=1),
    # not "every core" — n_jobs=-1 is joblib's spelling for that.
    # IngestionConfig.max_workers=None keeps its own, more intuitive public
    # meaning ("every core"); this translation is an orchestrate.py-internal
    # detail (spec §5 step 2). Getting this backwards would silently make
    # the whole module run sequentially by default.
    n_jobs = -1 if config.max_workers is None else config.max_workers

    tracks: list[Track] = []
    failures: list[IngestionFailure] = []
    seen_paths: set[str] = set()

    # All deduped paths are submitted as a single Parallel() call up front
    # (spec §5 step 3) — "queued" fires for every path at this one logical
    # submission point, independent of joblib's own internal dispatch
    # batching/scheduling.
    for path in deduped_paths:
        if on_progress is not None:
            on_progress(path, "queued")

    parallel = Parallel(n_jobs=n_jobs, backend=_backend, return_as="generator_unordered")
    results = parallel(delayed(_worker)(path, config) for path in deduped_paths)

    # A manual next()-loop rather than `for result in results:` — a crashed
    # loky worker surfaces as a TerminatedWorkerError raised from next()
    # (confirmed empirically), after which the generator is exhausted
    # (further next() calls immediately raise StopIteration) rather than
    # continuing to yield the remaining, still-pending results. loky can't
    # attribute the crash to a specific path, so the reconciliation pass
    # below accounts for every path that never produced a real result,
    # whether due to a crash or any other reason the generator fell short.
    while True:
        try:
            result = next(results)
        except StopIteration:
            break
        except Exception as exc:
            _logger.warning(
                "worker pool error surfaced from generator: %s: %s — remaining "
                "in-flight results for this batch are lost",
                type(exc).__name__,
                exc,
            )
            break

        if isinstance(result, Track):
            tracks.append(result)
            seen_paths.add(result.path)
            if on_progress is not None:
                on_progress(result.path, "completed")
        else:
            failures.append(result)
            seen_paths.add(result.path)
            if on_progress is not None:
                on_progress(result.path, "failed")

    for path in deduped_paths:
        if path not in seen_paths:
            failure = IngestionFailure(
                path=path,
                error="worker process crashed or its result was lost",
                error_type="WorkerCrash",
            )
            failures.append(failure)
            if on_progress is not None:
                on_progress(path, "failed")

    return IngestionResult(tracks=tracks, failures=failures)
