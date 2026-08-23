#!/usr/bin/env python3
"""CLI: fit a Platt scaling calibration from a labelled dataset.

Phase 3 of the OCR quality trust layer (design §11.3). Reads an
OCR-Quality-format JSON dump of ``(raw_confidence, quality_score)``
pairs, fits ``sigmoid(a * raw + b)`` on an 80% train split, evaluates
expected calibration error on the held-out 20%, and writes the
parameters to ``resources/calibration/{model_id}.json`` so the
runtime :mod:`omniscribe.core.ocr_quality.calibration` module can
pick them up on the next OCR run.

Input format (JSON array of objects, line-delimited JSONL is also
accepted by changing the file extension to ``.jsonl``)::

    [
      {"raw_confidence": 0.85, "quality_score": 1},
      {"raw_confidence": 0.42, "quality_score": 3},
      ...
    ]

The discrete ``quality_score`` (1=Excellent … 4=Poor per the
OCR-Quality paper) is mapped to a continuous target probability via
:data:`QUALITY_TO_PROBABILITY`. Higher scores → lower targets so the
calibration pushes raw confidences *down* when the model is
over-confident and *up* when it is under-confident.

Usage::

    uv run scripts/calibrate_model.py \
        --input path/to/records.json \
        --model-id qwen2_5_vl_72b \
        --output resources/calibration/qwen2_5_vl_72b.json

The default ``--output`` resolves to
``src/omniscribe/resources/calibration/{model_id}.json`` — the path
the runtime calibration module already looks at. ``--seed`` controls
the train/test split RNG; the script is deterministic for a given
seed.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from omniscribe.core.ocr_quality.calibration_fit import (
    fit_platt,
    sigmoid,
)

_LOG = logging.getLogger("scripts.calibrate_model")

# OCR-Quality scores (1=Excellent, 2=Good, 3=Fair, 4=Poor) mapped to
# continuous target probabilities. Spacing is roughly geometric so
# the loss function weights the boundary between Excellent and Good
# the same as between Fair and Poor.
QUALITY_TO_PROBABILITY: dict[int, float] = {
    1: 0.90,
    2: 0.65,
    3: 0.30,
    4: 0.10,
}

# Default split ratio; matches the 80/20 used in the design's
# regression-test acceptance criterion (§16 item 4).
DEFAULT_TRAIN_FRACTION: float = 0.8

# Minimum number of records to attempt a fit. Below this the
# optimiser has no signal and we surface an error rather than ship a
# garbage calibration file.
DEFAULT_MIN_RECORDS: int = 50


class CalibrationError(RuntimeError):
    """Raised when calibration fitting cannot complete."""


@dataclass(frozen=True)
class _Record:
    raw: float
    target: float


def _to_target(quality_score: int) -> float:
    if quality_score not in QUALITY_TO_PROBABILITY:
        raise CalibrationError(
            f"quality_score {quality_score} not in {sorted(QUALITY_TO_PROBABILITY)}"
        )
    return QUALITY_TO_PROBABILITY[quality_score]


def _parse_record(item: dict[str, object]) -> _Record | None:
    """Return a valid record or ``None`` to drop the row."""
    raw_obj = item.get("raw_confidence")
    score_obj = item.get("quality_score")
    if not isinstance(raw_obj, (int, float)) or isinstance(raw_obj, bool):
        return None
    if not isinstance(score_obj, int) or isinstance(score_obj, bool):
        return None
    raw = float(raw_obj)
    score = score_obj
    if not (0.0 <= raw <= 1.0):
        return None
    if score not in QUALITY_TO_PROBABILITY:
        return None
    return _Record(raw=raw, target=_to_target(score))


def load_records(path: Path) -> list[_Record]:
    """Read an OCR-Quality-format JSON file, dropping malformed rows."""
    if not path.exists():
        raise CalibrationError(f"input file not found: {path}")
    try:
        raw_text = path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationError(f"failed to read {path}: {exc}") from exc
    if not isinstance(data, list):
        raise CalibrationError(
            f"{path}: expected JSON array, got {type(data).__name__}"
        )
    records: list[_Record] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        record = _parse_record(item)
        if record is not None:
            records.append(record)
    return records


def _split(
    records: Sequence[_Record], *, train_fraction: float, seed: int
) -> tuple[list[_Record], list[_Record]]:
    """Deterministic 80/20 split (no replacement, preserves order after shuffle)."""
    if not 0.0 < train_fraction < 1.0:
        raise CalibrationError(
            f"train_fraction must be in (0, 1); got {train_fraction}"
        )
    rng = random.Random(seed)
    indices = list(range(len(records)))
    rng.shuffle(indices)
    cut = max(1, int(len(records) * train_fraction))
    train_idx = set(indices[:cut])
    train = [records[i] for i in range(len(records)) if i in train_idx]
    test = [records[i] for i in range(len(records)) if i not in train_idx]
    return train, test


def _expected_calibration_error(
    records: Iterable[_Record],
    *,
    a: float,
    b: float,
    bins: int = 10,
) -> float:
    """10-bin ECE — the standard calibration metric.

    Returns ``0.0`` for empty input (no observations to miscalibrate).
    """
    rows = [(sigmoid(a * r.raw + b), r.target) for r in records]
    if not rows:
        return 0.0
    bin_width = 1.0 / bins
    weighted_error = 0.0
    for i in range(bins):
        lo = i * bin_width
        hi = (i + 1) * bin_width
        in_bin = [
            (p, t) for p, t in rows if lo <= p < hi or (i == bins - 1 and p == hi)
        ]
        if not in_bin:
            continue
        avg_p = sum(p for p, _ in in_bin) / len(in_bin)
        avg_t = sum(t for _, t in in_bin) / len(in_bin)
        weighted_error += (len(in_bin) / len(rows)) * abs(avg_p - avg_t)
    return weighted_error


def fit_from_records(
    records: Sequence[_Record],
    *,
    seed: int = 42,
    train_fraction: float = DEFAULT_TRAIN_FRACTION,
    min_records: int = DEFAULT_MIN_RECORDS,
) -> dict[str, float | int]:
    """Fit Platt scaling on ``records`` and report calibration metrics."""
    if len(records) < min_records:
        raise CalibrationError(
            f"need at least {min_records} records to fit; got {len(records)}"
        )
    train, test = _split(records, train_fraction=train_fraction, seed=seed)
    if not train or not test:
        raise CalibrationError("train/test split produced an empty half")
    # ``fit_platt`` returns the plain tuple by default; we don't need the
    # iteration/loss metadata, so the default branch keeps the call site
    # tight. The runtime assertion narrows the union for mypy.
    fit = fit_platt(
        [r.raw for r in train],
        [r.target for r in train],
    )
    if not isinstance(fit, tuple):
        raise CalibrationError("fit_platt returned CalibrationFitResult unexpectedly")
    a, b = fit
    ece_after = _expected_calibration_error(test, a=a, b=b)
    ece_baseline = _expected_calibration_error(
        test,
        a=1.0,
        b=0.0,  # identity passthrough
    )
    return {
        "a": float(a),
        "b": float(b),
        "ece_after": ece_after,
        "ece_baseline": ece_baseline,
        "n_records": len(records),
        "n_train": len(train),
        "n_test": len(test),
        "seed": seed,
    }


def write_calibration(
    params: dict[str, float | int],
    *,
    model_id: str,
    output_path: Path,
) -> None:
    """Write a ``{a, b, metadata}`` JSON file the runtime can load."""
    payload = {
        "a": params["a"],
        "b": params["b"],
        "metadata": {
            "model_id": model_id,
            "ece_after": params["ece_after"],
            "ece_baseline": params["ece_baseline"],
            "n_records": params["n_records"],
            "n_train": params["n_train"],
            "n_test": params["n_test"],
            "seed": params["seed"],
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI args. ``--model-id`` is mandatory to prevent overwriting."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to OCR-Quality-format JSON records.",
    )
    parser.add_argument(
        "--model-id",
        required=True,
        help="Model identifier (used to name the output file).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path. Defaults to resources/calibration/{model_id}.json.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for the 80/20 train/test split (default: 42).",
    )
    parser.add_argument(
        "--train-fraction",
        type=float,
        default=DEFAULT_TRAIN_FRACTION,
        help="Train fraction for the hold-out split (default: 0.8).",
    )
    parser.add_argument(
        "--min-records",
        type=int,
        default=DEFAULT_MIN_RECORDS,
        help="Minimum record count to attempt a fit (default: 50).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)

    output_path = args.output
    if output_path is None:
        output_path = (
            PROJECT_ROOT
            / "src"
            / "omniscribe"
            / "resources"
            / "calibration"
            / f"{args.model_id}.json"
        )

    try:
        records = load_records(args.input)
        params = fit_from_records(
            records,
            seed=args.seed,
            train_fraction=args.train_fraction,
            min_records=args.min_records,
        )
    except CalibrationError as exc:
        _LOG.error("calibration failed: %s", exc)
        return 2

    write_calibration(params, model_id=args.model_id, output_path=output_path)
    _LOG.info(
        "wrote %s (a=%.4f b=%.4f ece=%.4f baseline=%.4f n=%d)",
        output_path,
        params["a"],
        params["b"],
        params["ece_after"],
        params["ece_baseline"],
        params["n_records"],
    )
    return 0


__all__ = [
    "DEFAULT_MIN_RECORDS",
    "DEFAULT_TRAIN_FRACTION",
    "QUALITY_TO_PROBABILITY",
    "CalibrationError",
    "fit_from_records",
    "load_records",
    "parse_args",
    "write_calibration",
]


if __name__ == "__main__":
    raise SystemExit(main())
