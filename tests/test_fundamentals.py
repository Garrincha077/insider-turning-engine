from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from insider_turning_engine.features.fundamentals import ValuationPrice, financial_evidence
from insider_turning_engine.ingestion.sec.company_facts import CompanyFactsResult, FinancialFact

NOW = datetime(2026, 3, 1, 22, tzinfo=UTC)
ACCEPTED = datetime(2026, 2, 1, 22, tzinfo=UTC)
END, START = date(2025, 12, 31), date(2025, 1, 1)


def fact(tag, value, *, unit="USD", start=None, end=END):
    return FinancialFact("0001234567", "us-gaap", tag, unit, Decimal(value), start, end,
        "0001234567-26-000001", ACCEPTED, date(2026, 2, 1), "10-K",
        "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/")


def facts():
    return CompanyFactsResult((fact("NetIncomeLoss", "10", start=START),
        fact("RevenueFromContractWithCustomerExcludingAssessedTax", "100", start=START),
        fact("Assets", "200"), fact("Liabilities", "50"),
        fact("StockholdersEquity", "100"),
        fact("StockholdersEquity", "80", end=START - timedelta(days=1)),
        fact("WeightedAverageNumberOfDilutedSharesOutstanding", "110", unit="shares", start=START),
        fact("WeightedAverageNumberOfDilutedSharesOutstanding", "100", unit="shares",
             start=date(2024, 1, 1), end=date(2024, 12, 31)),
        fact("EarningsPerShareDiluted", "2", unit="USD/shares", start=START)), ())


def panel(data=None, profile="OPERATING", price=None):
    return {row.name: row for row in financial_evidence(data or facts(), as_of=NOW,
        sector_profile=profile, price=price)}


def test_financial_metrics_use_explicit_matching_periods_and_preserve_sources():
    result = panel()
    assert result["annual_net_margin"].value == 10
    assert result["liabilities_to_assets"].value == 25
    assert round(result["annual_return_on_equity"].value, 6) == Decimal("11.111111")
    assert round(result["annual_diluted_share_change"].value, 6) == Decimal("10.000000")
    for key in ["annual_net_margin", "annual_return_on_equity"]:
        assert result[key].available_at == ACCEPTED
        assert result[key].accessions == ("0001234567-26-000001",)
    assert result["reported_annual_pe"].value is None


def test_financial_sector_leverage_and_reit_gaap_pe_are_not_generic_cheapness():
    price = ValuationPrice(Decimal("20"), date(2026, 2, 27), NOW, True,
                           "verified-source", "UNADJUSTED", "USD")
    financial = panel(profile="FINANCIAL", price=price)
    assert financial["liabilities_to_assets"].value is None
    assert financial["liabilities_to_assets"].reasons == ("NOT_COMPARABLE_FOR_SECTOR",)
    assert financial["annual_return_on_equity"].value is not None
    reit = panel(profile="REAL_ESTATE", price=price)
    assert reit["reported_annual_pe"].value is None
    assert reit["reported_annual_pe"].reasons == ("REIT_FFO_DATA_REQUIRED",)


def test_pe_needs_current_public_price_and_explicit_split_share_basis_proof():
    price = ValuationPrice(Decimal("20"), date(2026, 2, 27), NOW, True,
                           "verified-source", "UNADJUSTED", "USD")
    pe = panel(price=price)["reported_annual_pe"]
    assert pe.value == 10 and pe.available_at == NOW
    assert pe.price_source == "verified-source" and pe.price_session == price.session
    for invalid in [replace(price, available_at=NOW + timedelta(seconds=1)),
                    replace(price, share_basis_verified=False),
                    replace(price, adjustment_basis="ADJUSTED"),
                    replace(price, adjustment_basis="UNKNOWN"),
                    replace(price, currency="OTHER"),
                    replace(price, currency="UNKNOWN"),
                    replace(price, session=NOW.date() - timedelta(days=8)),
                    replace(price, price=Decimal("NaN")),
                    replace(price, price=Decimal("0"))]:
        assert panel(price=invalid)["reported_annual_pe"].value is None


def test_future_facts_never_change_panel_and_missing_inputs_do_not_become_neutral_scores():
    original = facts()
    future = tuple(replace(row, accepted_at=NOW + timedelta(seconds=1),
                           value=Decimal("999999")) for row in original.facts)
    assert panel(CompanyFactsResult((*original.facts, *future), ())) == panel(original)
    poisoned_prior = fact("WeightedAverageNumberOfDilutedSharesOutstanding", "1000000",
        unit="shares", start=date(2024, 1, 11), end=date(2025, 1, 10))
    poisoned_prior = replace(poisoned_prior, accepted_at=NOW + timedelta(seconds=1))
    assert panel(CompanyFactsResult((*original.facts, poisoned_prior), ())) == panel(original)
    empty = panel(CompanyFactsResult((), ()))
    assert all(row.value is None for row in empty.values())
    assert all(row.reasons for row in empty.values())


def test_newer_quarterly_balance_does_not_change_annual_roe_denominator():
    original = facts()
    quarter = fact("StockholdersEquity", "100000", end=date(2026, 2, 28))
    result = panel(CompanyFactsResult((*original.facts, quarter), ()))
    assert result["annual_return_on_equity"] == panel(original)["annual_return_on_equity"]


def test_profitability_loss_remains_negative_and_pe_does_not_become_negative_cheapness():
    original = facts()
    rows = tuple(replace(row, value=-row.value) if row.tag in {
        "NetIncomeLoss", "EarningsPerShareDiluted"} else row for row in original.facts)
    price = ValuationPrice(Decimal("20"), date(2026, 2, 27), NOW, True,
                           "verified-source", "UNADJUSTED", "USD")
    result = panel(CompanyFactsResult(rows, ()), price=price)
    assert result["annual_net_margin"].value == -10
    assert result["reported_annual_pe"].value is None
