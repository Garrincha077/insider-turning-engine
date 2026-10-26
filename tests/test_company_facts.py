from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from insider_turning_engine.ingestion.sec.company_facts import (
    CompanyFactsResult,
    normalize_company_facts,
    select_financial_fact,
)

CIK = "0001234567"
FIRST = "0001234567-26-000001"
LATER = "0001234567-26-000002"
AS_OF = datetime(2026, 3, 1, 18, tzinfo=UTC)
ACCEPTED = {FIRST: datetime(2026, 2, 10, 22, tzinfo=UTC),
            LATER: datetime(2026, 3, 2, 22, tzinfo=UTC)}


def payload():
    row = {"start": "2025-01-01", "end": "2025-12-31", "val": 100,
           "accn": FIRST, "form": "10-K", "filed": "2026-02-10", "fy": 2025,
           "fp": "FY", "frame": "CY2025"}
    return {"cik": 1234567, "facts": {"us-gaap": {"NetIncomeLoss": {"units": {
        "USD": [row]}}}}}


def normalize(value=None, **kwargs):
    return normalize_company_facts(value or payload(), issuer_cik=CIK,
        acceptance_by_accession=ACCEPTED, as_of=kwargs.get("as_of", AS_OF),
        concepts={"us-gaap": ["NetIncomeLoss"]})


def select(facts, **kwargs):
    result = (facts if isinstance(facts, CompanyFactsResult)
              else CompanyFactsResult(tuple(facts), ()))
    return select_financial_fact(result, taxonomy="us-gaap", tag="NetIncomeLoss",
        unit=kwargs.get("unit", "USD"), as_of=kwargs.get("as_of", AS_OF),
        kind=kwargs.get("kind", "annual"))


def test_reported_value_preserves_exact_unit_period_accession_and_acceptance():
    result = normalize()
    assert not result.issues and len(result.facts) == 1
    fact = select(result.facts).fact
    assert fact.value == Decimal("100") and fact.unit == "USD"
    assert fact.start == date(2025, 1, 1) and fact.end == date(2025, 12, 31)
    assert fact.accepted_at == ACCEPTED[FIRST] and fact.accession == FIRST
    assert fact.source_url.endswith("/1234567/000123456726000001/")


def test_future_restated_value_cannot_change_earlier_fact_or_selection():
    document = payload()
    rows = document["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"]
    rows.append({**rows[0], "accn": LATER, "val": 999, "form": "10-K/A", "filed": "2026-03-02"})
    before = normalize()
    assert normalize(document) == before
    later = normalize(document, as_of=datetime(2026, 3, 3, tzinfo=UTC))
    assert select(later.facts).fact.value == Decimal("100")
    assert select(later.facts, as_of=datetime(2026, 3, 3, tzinfo=UTC)).fact.value == Decimal("999")
    rows.reverse()
    assert normalize(document, as_of=datetime(2026, 3, 3, tzinfo=UTC)) == later


def test_missing_acceptance_never_uses_filed_date_or_frame_as_publication_time():
    result = normalize_company_facts(payload(), issuer_cik=CIK,
        acceptance_by_accession={}, as_of=AS_OF, concepts={"us-gaap": ["NetIncomeLoss"]})
    assert not result.facts
    assert result.issues[0].code == "FINANCIAL_ACCEPTANCE_MISSING"
    assert select(result.facts).reason == "MISSING_FINANCIAL_FACT"


def test_replay_duplicates_do_not_grow_and_conflicts_withhold_entire_context():
    document = payload()
    rows = document["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"]
    rows.append(deepcopy(rows[0]))
    assert normalize(document) == normalize()
    rows.append({**rows[0], "val": 101})
    result = normalize(document)
    assert not result.facts and result.issues[0].code == "CONFLICTING_FINANCIAL_FACTS"
    rows.reverse()
    assert normalize(document) == result


def test_conflicted_newer_revision_does_not_resurrect_older_reported_value():
    document = payload()
    rows = document["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"]
    rows.extend([{**rows[0], "accn": LATER, "form": "10-K/A", "filed": "2026-03-02",
                  "val": value} for value in (101, 102)])
    later = datetime(2026, 3, 3, tzinfo=UTC)
    result = normalize(document, as_of=later)
    assert select(result, as_of=later).reason == "CONFLICTING_FINANCIAL_FACTS"
    assert select(result).fact.value == Decimal("100")  # Conflict not public yet.


@pytest.mark.parametrize("change", [
    {"val": True}, {"val": "NaN"}, {"val": "Infinity"}, {"form": "4"},
    {"end": "2026-04-01"}, {"filed": "2026-02-11"}, {"start": "2026-01-01"},
])
def test_invalid_value_form_clock_or_period_is_quarantined(change):
    document = payload()
    document["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][0].update(change)
    result = normalize(document)
    assert not result.facts and result.issues[0].code == "INVALID_FINANCIAL_FACT"


def test_losses_remain_negative_and_missing_unit_is_not_converted_or_imputed():
    document = payload()
    units = document["facts"]["us-gaap"]["NetIncomeLoss"]["units"]
    units["USD"][0]["val"] = -100
    units["EUR"] = [deepcopy(units["USD"][0])]
    result = normalize(document)
    assert select(result.facts).fact.value == -100
    assert select(result.facts, unit="USD/shares").fact is None
    assert result.issues[0].code == "UNSUPPORTED_FINANCIAL_UNIT"


def test_quarter_does_not_consume_ytd_and_53_week_year_is_supported():
    fact = normalize().facts[0]
    assert select([replace(fact, start=date(2024, 12, 26))]).reason == "AVAILABLE"
    ytd = replace(fact, start=date(2025, 1, 1), end=date(2025, 9, 30))
    assert select([ytd], kind="quarter").fact is None
    quarter = replace(ytd, start=date(2025, 7, 1))
    assert select([ytd, quarter], kind="quarter").fact == quarter
    instant = replace(fact, start=None)
    assert select([instant], kind="instant").fact == instant
    assert select([instant], kind="annual").fact is None


def test_conflicting_same_time_filings_are_not_lexically_selected_by_return_value():
    fact = normalize().facts[0]
    assert select([fact, replace(fact, accession=LATER, value=Decimal("999"))]).reason \
        == "CONFLICTING_FINANCIAL_FACTS"


def test_wrong_issuer_and_naive_clocks_fail_before_analysis():
    with pytest.raises(ValueError, match="CIK"):
        normalize({**payload(), "cik": 999})
    with pytest.raises(ValueError, match="timezone"):
        normalize(as_of=datetime(2026, 3, 1))


def test_us_evening_filing_is_joined_by_new_york_civil_date_not_utc_date():
    result = normalize_company_facts(payload(), issuer_cik=CIK,
        acceptance_by_accession={FIRST: datetime(2026, 2, 11, 1, tzinfo=UTC)},
        as_of=AS_OF, concepts={"us-gaap": ["NetIncomeLoss"]})
    assert not result.issues and len(result.facts) == 1
