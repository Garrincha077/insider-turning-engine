"""Small filing-backed financial evidence panel, never a fabricated value score.

Annual flow metrics stay labelled annual (not TTM). Instantaneous metrics are
matched on the same balance date, and dilution uses comparable annual periods.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from insider_turning_engine.domain.session_calendar import session_lag
from insider_turning_engine.ingestion.sec.company_facts import (
    CompanyFactsResult,
    FinancialFact,
    select_financial_fact,
)


@dataclass(frozen=True)
class FundamentalMetric:
    name: str
    value: Decimal | None
    unit: str
    period_start: date | None
    period_end: date | None
    accessions: tuple[str, ...]
    available_at: datetime | None
    reasons: tuple[str, ...]
    source_urls: tuple[str, ...] = ()
    price_source: str | None = None
    price_session: date | None = None


@dataclass(frozen=True)
class ValuationPrice:
    price: Decimal
    session: date
    available_at: datetime
    share_basis_verified: bool
    source: str
    adjustment_basis: Literal["UNADJUSTED", "ADJUSTED", "UNKNOWN"] = "UNKNOWN"
    currency: Literal["USD", "OTHER", "UNKNOWN"] = "UNKNOWN"


def financial_evidence(
    facts: CompanyFactsResult, *, as_of: datetime,
    sector_profile: Literal["OPERATING", "FINANCIAL", "REAL_ESTATE", "UNKNOWN"],
    price: ValuationPrice | None = None,
) -> tuple[FundamentalMetric, ...]:
    """No score/neutral imputation, financial-sector leverage or fake cheap label.

    A price is usable for P/E only with explicit share-basis evidence, a recent
    session and an available timestamp. Missing this proof withholds P/E but
    does not erase independent SEC profitability or balance-sheet observations.
    """
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("fundamental as_of must be timezone-aware")
    if sector_profile not in {"OPERATING", "FINANCIAL", "REAL_ESTATE", "UNKNOWN"}:
        raise ValueError("unknown financial sector profile")

    def pick(tag: str, unit: str = "USD", kind: Literal["instant", "annual"] = "instant",
             *, start: date | None = None, end: date | None = None) -> FinancialFact | None:
        return select_financial_fact(facts, taxonomy="us-gaap", tag=tag, unit=unit,
            as_of=as_of, kind=kind, start=start, end=end).fact

    def metric(name: str, value: Decimal | None, unit: str,
               rows: tuple[FinancialFact, ...], *reasons: str) -> FundamentalMetric:
        latest_end = max((row.end for row in rows), default=None)
        # An intentionally older comparison period (ROE opening equity or prior
        # annual shares) is not evidence that the newest reported metric is stale.
        reasons = tuple(sorted({*reasons, *(
            ["STALE_FINANCIAL_PERIOD"] if latest_end is not None
            and (as_of.date() - latest_end).days > 550 else [])}))
        return FundamentalMetric(name, value, unit,
            min((row.start for row in rows if row.start is not None), default=None),
            max((row.end for row in rows), default=None),
            tuple(sorted({row.accession for row in rows})),
            max((row.accepted_at for row in rows), default=None), reasons,
            tuple(sorted({row.source_url for row in rows})))

    income = pick("NetIncomeLoss", kind="annual")
    # Do not substitute another tag with subtly different economic meaning.
    revenue = (pick("RevenueFromContractWithCustomerExcludingAssessedTax", kind="annual",
                    start=income.start, end=income.end) if income else None)
    annual = (income, revenue) if income and revenue else ()
    margin = (income.value / revenue.value * 100
              if income and revenue and revenue.value > 0 else None)
    outputs = [metric("annual_net_margin", margin, "percent", annual,
        *(() if margin is not None else ("MISSING_COMPARABLE_ANNUAL_INCOME_REVENUE",)))]

    assets = pick("Assets")
    liabilities = pick("Liabilities", end=assets.end) if assets else None
    balance = (assets, liabilities) if assets and liabilities else ()
    leverage = (liabilities.value / assets.value * 100 if assets and liabilities
                and assets.value > 0 and liabilities.value >= 0 else None)
    if sector_profile != "OPERATING":
        leverage = None
    outputs.append(metric("liabilities_to_assets", leverage, "percent", balance,
        *(() if leverage is not None else
          ("NOT_COMPARABLE_FOR_SECTOR",) if sector_profile != "OPERATING"
          else ("MISSING_COMPARABLE_BALANCE_SHEET",))))

    # ROE uses equity at both ends of the same reported income year, never a
    # newer quarterly denominator paired with stale annual earnings.
    equity_end = pick("StockholdersEquity", end=income.end) if income else None
    equity_start = (pick("StockholdersEquity", end=income.start - timedelta(days=1))
                    if income and income.start else None)
    roe_rows = (income, equity_start, equity_end) if income and equity_start and equity_end else ()
    roe = (income.value / ((equity_start.value + equity_end.value) / 2) * 100
           if income and equity_start and equity_end
           and equity_start.value > 0 and equity_end.value > 0 else None)
    outputs.append(metric("annual_return_on_equity", roe, "percent", roe_rows,
        *(() if roe is not None else ("MISSING_COMPARABLE_ANNUAL_EQUITY",))))

    shares = pick("WeightedAverageNumberOfDilutedSharesOutstanding", "shares", "annual")
    previous = None
    if shares:
        candidates = [row for row in (*facts.facts, *facts.blocked_contexts)
                      if row.taxonomy == "us-gaap" and row.tag == shares.tag
                      and row.unit == "shares"
                      and row.accepted_at <= as_of and row.end <= as_of.date()
                      and row.start is not None and 350 <= (row.end - row.start).days + 1 <= 380
                      and 350 <= (shares.end - row.end).days <= 380]
        if candidates:
            previous_end = max(row.end for row in candidates)
            previous = pick(shares.tag, "shares", "annual", end=previous_end)
    share_rows = (shares, previous) if shares and previous else ()
    growth = ((shares.value / previous.value - 1) * 100
              if shares and previous and shares.value > 0 and previous.value > 0 else None)
    outputs.append(metric("annual_diluted_share_change", growth, "percent", share_rows,
        *(() if growth is not None else ("MISSING_COMPARABLE_DILUTED_SHARES",))))

    eps = pick("EarningsPerShareDiluted", "USD/shares", "annual")
    price_valid = (price is not None and price.available_at.tzinfo is not None
                   and price.available_at <= as_of and price.session <= as_of.date()
                   and (lag := session_lag(price.session, as_of=as_of)) is not None and lag <= 1
                   and price.share_basis_verified and price.adjustment_basis == "UNADJUSTED"
                   and price.currency == "USD"
                   and price.price.is_finite()
                   and price.price > 0 and bool(price.source.strip()))
    annual_pe = price.price / eps.value if price_valid and price and eps and eps.value > 0 else None
    if sector_profile == "REAL_ESTATE":
        annual_pe = None  # GAAP EPS is not substituted for FFO/AFFO in a REIT route.
    reasons = (() if annual_pe is not None else
               ("REIT_FFO_DATA_REQUIRED",) if sector_profile == "REAL_ESTATE" else
               ("PRICE_SHARE_BASIS_UNVERIFIED",) if not price_valid else
               ("NONPOSITIVE_OR_MISSING_ANNUAL_EPS",))
    pe = metric("reported_annual_pe", annual_pe, "multiple", (eps,) if eps else (), *reasons)
    if annual_pe is not None and eps and price:
        pe = replace(pe, available_at=max(eps.accepted_at, price.available_at),
                     price_source=price.source, price_session=price.session)
    outputs.append(pe)
    return tuple(outputs)
