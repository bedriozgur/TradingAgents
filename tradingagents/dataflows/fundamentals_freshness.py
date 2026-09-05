"""Fundamentals recency warnings and fallback metadata for quarterly statements.

This module does not verify the newest public filing. Its 120-day boundary is
only a heuristic for deciding whether configured fallback providers should be
queried and whether the retrieved period needs a visible staleness warning.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from io import StringIO

# Heuristic warning threshold only. It does not verify exchange announcements,
# SEC filings, investor-relations releases, or the newest publicly available period.
QUARTERLY_STALE_AFTER_DAYS = 120
QUARTERLY_STATEMENT_METHODS = {
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
}


@dataclass(frozen=True)
class QuarterlyResultAssessment:
    output: str
    status: str
    newest_period: date | None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return None


def _newest_json_period(payload: dict) -> date | None:
    periods = [
        _parse_date(report.get("fiscalDateEnding"))
        for report in payload.get("quarterlyReports", [])
        if isinstance(report, dict)
    ]
    return max((period for period in periods if period is not None), default=None)


def _newest_csv_period(result: str) -> date | None:
    csv_text = "\n".join(
        line for line in result.splitlines() if line and not line.startswith("#")
    )
    try:
        header = next(csv.reader(StringIO(csv_text)))
    except (StopIteration, csv.Error):
        return None
    periods = [_parse_date(value) for value in header[1:]]
    return max((period for period in periods if period is not None), default=None)


def _freshness_metadata(provider: str, newest_period: date | None, analysis_date: str | None):
    metadata: dict[str, str | int] = {
        "source_provider": provider,
        "frequency": "quarterly",
        "freshness_threshold_days": QUARTERLY_STALE_AFTER_DAYS,
        "freshness_basis": (
            "Heuristic age check only; newest public filing was not independently verified."
        ),
    }
    if newest_period is not None:
        metadata["newest_retrieved_reporting_period"] = newest_period.isoformat()

    as_of = _parse_date(analysis_date)
    if newest_period is None or as_of is None:
        metadata["freshness_status"] = "UNKNOWN"
        metadata["warning"] = (
            "WARNING: Quarterly-data freshness could not be established. Do not describe "
            "any retrieved period as latest."
        )
        return metadata

    age_days = (as_of - newest_period).days
    metadata["freshness_as_of"] = as_of.isoformat()
    metadata["reporting_period_age_days"] = age_days
    if 0 <= age_days <= QUARTERLY_STALE_AFTER_DAYS:
        metadata["freshness_status"] = "RECENT"
    else:
        metadata["freshness_status"] = "POTENTIALLY_STALE"
        metadata["warning"] = (
            "WARNING: The newest retrieved quarterly financial period may be stale relative "
            f"to the analysis date ({age_days} days old; threshold "
            f"{QUARTERLY_STALE_AFTER_DAYS} days). Do not describe it as latest."
        )
    return metadata


def assess_quarterly_result(
    method: str,
    provider: str,
    result: str,
    args: tuple,
    kwargs: dict,
) -> QuarterlyResultAssessment | None:
    """Assess and annotate a quarterly result, or return ``None`` when inapplicable."""
    if method not in QUARTERLY_STATEMENT_METHODS:
        return None

    frequency = kwargs.get("freq", args[1] if len(args) > 1 else "quarterly")
    if str(frequency).lower() != "quarterly":
        return None
    analysis_date = kwargs.get("curr_date", args[2] if len(args) > 2 else None)

    try:
        payload = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        payload = None

    if isinstance(payload, dict):
        newest_period = _newest_json_period(payload)
        metadata = _freshness_metadata(provider, newest_period, analysis_date)
        payload["_tradingagents_metadata"] = metadata
        return QuarterlyResultAssessment(
            json.dumps(payload), str(metadata["freshness_status"]), newest_period
        )

    newest_period = _newest_csv_period(result)
    metadata = _freshness_metadata(provider, newest_period, analysis_date)
    lines = [
        f"# Source provider: {metadata['source_provider']}",
        "# Newest retrieved reporting period: "
        + str(metadata.get("newest_retrieved_reporting_period", "unknown")),
        f"# Freshness status: {metadata['freshness_status']}",
        f"# Freshness basis: {metadata['freshness_basis']}",
    ]
    if warning := metadata.get("warning"):
        lines.append(f"# {warning}")
    return QuarterlyResultAssessment(
        "\n".join(lines) + "\n" + result,
        str(metadata["freshness_status"]),
        newest_period,
    )


def annotate_quarterly_result(
    method: str,
    provider: str,
    result: str,
    args: tuple,
    kwargs: dict,
) -> str:
    """Attach quarterly metadata while preserving non-quarterly results unchanged."""
    assessment = assess_quarterly_result(method, provider, result, args, kwargs)
    return assessment.output if assessment is not None else result
