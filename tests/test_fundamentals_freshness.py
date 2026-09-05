"""Regression coverage for quarterly fundamentals source/freshness metadata."""

import json
from pathlib import Path

import pytest

from tradingagents.dataflows.fundamentals_freshness import annotate_quarterly_result

FIXTURES = Path(__file__).parent / "fixtures"


def _affirmative_latest_claims(text: str) -> list[str]:
    """Ignore warning prohibitions and return lines that affirmatively label data latest."""
    return [
        line
        for line in text.splitlines()
        if "latest" in line.lower() and "do not describe" not in line.lower()
    ]


@pytest.mark.unit
def test_stale_csv_period_has_source_date_and_visible_warning():
    result = (FIXTURES / "nvda_yfinance_quarterly_2026_04_30.csv").read_text()
    annotated = annotate_quarterly_result(
        "get_income_statement",
        "yfinance",
        result,
        ("NVDA", "quarterly", "2026-09-05"),
        {},
    )
    assert "# Source provider: yfinance" in annotated
    assert "# Newest retrieved reporting period: 2026-04-30" in annotated
    assert "# Freshness status: POTENTIALLY_STALE" in annotated
    assert "# WARNING:" in annotated
    assert _affirmative_latest_claims(annotated) == []


@pytest.mark.unit
def test_recent_json_period_preserves_source_date_without_claiming_latest():
    result = json.dumps({
        "symbol": "NVDA",
        "quarterlyReports": [{"fiscalDateEnding": "2026-07-27", "revenue": "1"}],
    })
    annotated = annotate_quarterly_result(
        "get_income_statement",
        "alpha_vantage",
        result,
        ("NVDA", "quarterly", "2026-09-05"),
        {},
    )
    metadata = json.loads(annotated)["_tradingagents_metadata"]
    assert metadata["source_provider"] == "alpha_vantage"
    assert metadata["newest_retrieved_reporting_period"] == "2026-07-27"
    assert metadata["freshness_status"] == "RECENT"
    assert "not independently verified" in metadata["freshness_basis"]
    assert "warning" not in metadata
    assert _affirmative_latest_claims(annotated) == []


@pytest.mark.unit
def test_unknown_period_freshness_warns_and_does_not_claim_latest():
    annotated = annotate_quarterly_result(
        "get_cashflow",
        "yfinance",
        "unparseable statement",
        ("NVDA", "quarterly", "2026-09-05"),
        {},
    )
    assert "Newest retrieved reporting period: unknown" in annotated
    assert "Freshness status: UNKNOWN" in annotated
    assert "WARNING:" in annotated
    assert _affirmative_latest_claims(annotated) == []
