"""Command-line entry points for reproducible local and scheduled runs."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import Annotated, Any, cast

import httpx
import polars as pl
import typer

from .backtest import (
    BacktestPeriod,
    BacktestSignal,
    EvaluationStage,
    build_backtest_report,
    run_backtest,
)
from .export.dashboard import (
    DashboardExportError,
    dashboard_publication_policy,
    validate_dashboard_directory,
)
from .export.dashboard import (
    export_dashboard as publish_dashboard,
)
from .features.price import price_features
from .ingestion.market import (
    CsvMarketDataProvider,
    StooqMarketDataProvider,
    probe_market_coverage,
)
from .ingestion.sec import (
    SECDailyIndexSource,
    SECIncrementalSource,
    SecRawRecord,
    decode_cursor,
    parse_sec_filing,
    stage_quarter,
    validate_sec_user_agent,
)
from .notifications import (
    AlertCandidate,
    AlertType,
    EmailHTTPChannel,
    NotificationPolicy,
    NotificationPolicyError,
    Severity,
    SQLiteOutbox,
    TelegramHTTPChannel,
    build_settings_status,
    format_plain,
    load_notification_policy,
    preview_email_html,
    preview_telegram_html,
)
from .scoring import ScoreEngine

app = typer.Typer(
    name="insider-turning",
    help="Build point-in-time insider-turning research snapshots.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)

PathOption = Annotated[Path | None, typer.Option()]


def _channel_names(value: str, policy: NotificationPolicy | None = None) -> tuple[str, ...]:
    normalized = value.strip().lower()
    if normalized not in {"telegram", "email", "all"}:
        raise typer.BadParameter("--channel must be telegram, email, or all")
    selected = ("telegram", "email") if normalized == "all" else (normalized,)
    if policy is None:
        return selected
    if normalized == "all":
        if not policy.enabled_channels:
            raise typer.BadParameter("no notification channels are enabled")
        return policy.enabled_channels
    disabled = [name for name in selected if name not in policy.enabled_channels]
    if disabled:
        raise typer.BadParameter(
            "requested channels are disabled by notification policy: " + ", ".join(disabled)
        )
    return selected


def _telegram_channel() -> TelegramHTTPChannel:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise typer.BadParameter("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")

    def transport(url: str, payload: Any) -> httpx.Response:
        return httpx.post(url, data=payload, timeout=20.0)

    return TelegramHTTPChannel(token, chat_id, transport)


def _email_channel() -> EmailHTTPChannel:
    api_key = os.getenv("EMAIL_API_KEY", "")
    sender = os.getenv("ALERT_EMAIL_FROM", "")
    recipient = os.getenv("ALERT_EMAIL_TO", "")
    if not api_key or not sender or not recipient:
        raise typer.BadParameter(
            "EMAIL_API_KEY, ALERT_EMAIL_FROM, and ALERT_EMAIL_TO are required"
        )

    def transport(
        url: str, payload: Mapping[str, Any], headers: Mapping[str, str]
    ) -> httpx.Response:
        return httpx.post(url, json=payload, headers=headers, timeout=20.0)

    return EmailHTTPChannel(api_key, sender, recipient, transport)


def _configured_channels(
    names: tuple[str, ...],
) -> tuple[TelegramHTTPChannel | EmailHTTPChannel, ...]:
    return tuple(_telegram_channel() if name == "telegram" else _email_channel() for name in names)


def _echo(value: dict[str, Any]) -> None:
    typer.echo(json.dumps(value, indent=2, sort_keys=True, default=str))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _recover_cursor(cursor_file: Path) -> tuple[str | None, Path | None]:
    """Read a durable SEC cursor, preserving malformed state for inspection.

    Restarting the source cursor can replay filings, which downstream
    idempotency keys safely collapse.  Keeping the malformed input instead of
    overwriting it makes that recovery explicit and auditable.
    """

    if not cursor_file.exists():
        return None, None
    try:
        payload = json.loads(cursor_file.read_text("utf-8"))
        cursor = payload.get("cursor") if isinstance(payload, dict) else None
        if cursor is not None:
            cursor = str(cursor)
            decode_cursor(cursor)
        return cursor, None
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        recovered = cursor_file.with_name(f"{cursor_file.name}.corrupt-{stamp}")
        os.replace(cursor_file, recovered)
        return None, recovered


@app.command("backfill-sec")
def backfill_sec(
    year: Annotated[int | None, typer.Option(help="SEC dataset year.")] = None,
    quarter: Annotated[int | None, typer.Option(min=1, max=4)] = None,
    cache_dir: Annotated[Path, typer.Option()] = Path("data/cache/sec"),
    staging_dir: Annotated[Path, typer.Option()] = Path("data/staging/sec"),
    execute: Annotated[bool, typer.Option(help="Allow the SEC network request.")] = False,
) -> None:
    """Download and stage one official SEC quarterly bulk archive."""

    if year is None or quarter is None or not execute:
        _echo(
            {
                "command": "backfill-sec",
                "status": "DRY_RUN",
                "year": year,
                "quarter": quarter,
                "requires": ["--year", "--quarter", "--execute", "SEC_USER_AGENT"],
            }
        )
        return
    user_agent = os.getenv("SEC_USER_AGENT", "").strip()
    try:
        user_agent = validate_sec_user_agent(user_agent)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    result = stage_quarter(year, quarter, cache_dir, staging_dir, user_agent)
    _echo(
        {
            "command": "backfill-sec",
            "status": "SUCCEEDED",
            "partition": str(result.partition_path),
            "tables": len(result.parquet_paths),
            "quarantinedRows": result.quarantined_rows,
        }
    )


@app.command("backfill-sec-history")
def backfill_sec_history(
    start_year: Annotated[int, typer.Option(min=2006)] = 2006,
    start_quarter: Annotated[int, typer.Option(min=1, max=4)] = 1,
    end_year: Annotated[int | None, typer.Option(min=2006)] = None,
    end_quarter: Annotated[int | None, typer.Option(min=1, max=4)] = None,
    cache_dir: Annotated[Path, typer.Option()] = Path("data/cache/sec"),
    staging_dir: Annotated[Path, typer.Option()] = Path("data/staging/sec"),
    execute: Annotated[bool, typer.Option()] = False,
) -> None:
    """Resume official completed-quarter staging (not canonical signal history)."""
    from .ingestion.sec.history import backfill_history, last_completed_quarter, quarter_range

    if (end_year is None) != (end_quarter is None):
        raise typer.BadParameter("supply both --end-year and --end-quarter")
    end = ((end_year, end_quarter) if end_year is not None and end_quarter is not None
           else last_completed_quarter(datetime.now(UTC).date()))
    try:
        periods = quarter_range((start_year, start_quarter), end)
        if end > last_completed_quarter(datetime.now(UTC).date()):
            raise ValueError("cannot backfill an incomplete quarter")
        if not execute:
            _echo({"status": "DRY_RUN", "quarters": periods, "canonicalReady": False})
            return
        user_agent = validate_sec_user_agent(os.getenv("SEC_USER_AGENT", ""))
        report = backfill_history(
            cache_dir=cache_dir, staging_dir=staging_dir, user_agent=user_agent,
            start=(start_year, start_quarter), end=end,
            progress=lambda message: typer.echo(message, err=True),
        )
    except (ValueError, RuntimeError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    _echo(report)
    if report["status"] != "STAGED":
        raise typer.Exit(1)


@app.command("inventory-sec-activity")
def inventory_sec_activity(
    as_of: Annotated[str, typer.Option(help="Conservative availability date, YYYY-MM-DD.")],
    staging_dir: Annotated[Path, typer.Option()] = Path("data/staging/sec"),
    output: Annotated[Path, typer.Option()] = Path("data/staging/sec/activity-inventory.json"),
) -> None:
    """Inspect 365-day acquisition candidates; never produces scores or enables alerts."""
    from .ingestion.sec.history import activity_inventory

    try:
        report = activity_inventory(staging_dir, as_of=date.fromisoformat(as_of))
    except (ValueError, OSError, KeyError, TypeError, pl.exceptions.PolarsError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    _write_json(output, report)
    _echo({key: value for key, value in report.items() if key != "candidateIssuerCiks"})


@app.command("update-sec")
def update_sec(
    xml: PathOption = None,
    accession: Annotated[str | None, typer.Option()] = None,
    source_url: Annotated[str | None, typer.Option()] = None,
    accepted_at: Annotated[str | None, typer.Option(help="ISO SEC acceptance timestamp.")] = None,
    daily_index_date: Annotated[
        str | None,
        typer.Option(help="Official EDGAR daily-index date (YYYY-MM-DD)."),
    ] = None,
    cik_file: PathOption = None,
    since: Annotated[str | None, typer.Option()] = None,
    through: Annotated[str | None, typer.Option()] = None,
    cursor_file: Annotated[Path, typer.Option()] = Path("data/state/sec.cursor"),
    run_id: Annotated[str | None, typer.Option(help="Immutable pipeline run identifier.")] = None,
    execute: Annotated[bool, typer.Option(help="Allow SEC network requests.")] = False,
    output: Annotated[Path, typer.Option()] = Path("data/staging/sec-incremental.json"),
) -> None:
    """Normalize one fetched ownership XML; scheduled runs use the incremental adapter."""

    selected_modes = sum(value is not None for value in (xml, daily_index_date, cik_file))
    if selected_modes > 1:
        raise typer.BadParameter("choose exactly one of --xml, --daily-index-date, or --cik-file")
    if selected_modes == 0 or (xml is None and not execute):
        _echo(
            {
                "command": "update-sec",
                "status": "DRY_RUN",
                "alternatives": [
                    ["--xml", "--accession", "--source-url"],
                    ["--daily-index-date", "--execute", "SEC_USER_AGENT"],
                    ["--cik-file", "--execute", "SEC_USER_AGENT"],
                ],
            }
        )
        return
    records: list[dict[str, Any]] = []
    quarantines: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    recovered_cursor: Path | None = None
    cursor: str | None = None
    next_cursor: str | None = None
    resolved_run_id = run_id or f"run_cli_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    if re.fullmatch(r"run_[A-Za-z0-9_-]{16,64}", resolved_run_id) is None:
        raise typer.BadParameter("--run-id must match run_[A-Za-z0-9_-]{16,64}")
    if xml is not None:
        if accession is None or source_url is None:
            raise typer.BadParameter("--accession and --source-url are required with --xml")
        accepted = datetime.fromisoformat(accepted_at) if accepted_at else datetime.now(UTC)
        if accepted.tzinfo is None:
            raise typer.BadParameter("--accepted-at must include a timezone")
        result = parse_sec_filing(
            xml.read_bytes(),
            {
                "accession_number": accession,
                "source_url": source_url,
                "accepted_at": accepted,
                "observed_at": datetime.now(UTC),
                "run_id": resolved_run_id,
            },
        )
        records.extend(record.canonical_dump() for record in result.records)
        quarantines.extend(item.model_dump(mode="json") for item in result.quarantines)
    elif daily_index_date is not None:
        try:
            index_day = date.fromisoformat(daily_index_date)
        except ValueError as exc:
            raise typer.BadParameter("--daily-index-date must be YYYY-MM-DD") from exc
        user_agent = os.getenv("SEC_USER_AGENT", "").strip()
        try:
            user_agent = validate_sec_user_agent(user_agent)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        daily_source = SECDailyIndexSource(
            user_agent,
            cache_dir="data/cache/sec-daily-index",
        )
        try:
            page = daily_source.fetch_day(index_day)
            quarantines.extend(item.model_dump(mode="json") for item in page.quarantines)
            for raw in page.records:
                if raw.payload is None:
                    failures.append(
                        {
                            "providerRecordId": raw.provider_record_id,
                            "status": "permanent-invalid",
                            "message": "daily-index filing has no ownership XML payload",
                        }
                    )
                    continue
                parsed = parse_sec_filing(
                    raw.payload,
                    {
                        "accession_number": raw.accession_number,
                        "source_url": raw.source_url,
                        "accepted_at": raw.accepted_at,
                        "observed_at": raw.retrieved_at,
                        "run_id": resolved_run_id,
                    },
                )
                records.extend(record.canonical_dump() for record in parsed.records)
                quarantines.extend(item.model_dump(mode="json") for item in parsed.quarantines)
        finally:
            daily_source.close()
    else:
        assert cik_file is not None
        user_agent = os.getenv("SEC_USER_AGENT", "").strip()
        try:
            user_agent = validate_sec_user_agent(user_agent)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        cik_text = cik_file.read_text("utf-8")
        ciks = [
            item.strip()
            for item in cik_text.replace(",", "\n").splitlines()
            if item.strip() and not item.strip().startswith("#")
        ]
        if not ciks or any(not cik.isdigit() or len(cik) > 10 for cik in ciks):
            raise typer.BadParameter("CIK file must contain one or more 1-10 digit CIKs")
        ciks = list(dict.fromkeys(ciks))
        incremental_source = SECIncrementalSource(
            ciks,
            user_agent,
            cache_dir="data/cache/sec-incremental",
            run_id=resolved_run_id,
        )
        cursor, recovered_cursor = _recover_cursor(cursor_file)
        page = incremental_source.fetch(cursor, through, since=since)
        next_cursor = page.next_cursor
        quarantines.extend(item.model_dump(mode="json") for item in page.quarantines)
        for reference in page.records:
            fetched = incremental_source.get(reference.provider_record_id)
            if isinstance(fetched, SecRawRecord):
                parsed = incremental_source.normalize(fetched)
                records.extend(record.canonical_dump() for record in parsed.records)
                quarantines.extend(item.model_dump(mode="json") for item in parsed.quarantines)
            else:
                failures.append(
                    {
                        "providerRecordId": reference.provider_record_id,
                        "status": fetched.status.value,
                        "message": fetched.message,
                    }
                )
    payload = {"records": records, "quarantines": quarantines, "failures": failures}
    # The output is written and flushed before a cursor is committed.  Any
    # fetch, normalization, quarantine, or output problem leaves the old
    # checkpoint intact so the whole page is safely replayed.
    _write_json(output, payload)
    incomplete = bool(quarantines or failures)
    cursor_advanced = False
    if cik_file is not None and not incomplete and next_cursor and next_cursor != cursor:
        _write_json(cursor_file, {"cursor": next_cursor})
        cursor_advanced = True
    status = "FAILED" if failures else "QUARANTINED" if quarantines else "SUCCEEDED"
    _echo(
        {
            "command": "update-sec",
            "status": status,
            "records": len(records),
            "quarantines": len(quarantines),
            "failures": failures,
            "output": str(output),
            "cursorRecovered": (
                str(recovered_cursor) if cik_file is not None and recovered_cursor else None
            ),
            "cursorAdvanced": cursor_advanced,
        }
    )
    if incomplete:
        raise typer.Exit(1)


@app.command("ingest-sec-day")
def ingest_sec_day(
    day: Annotated[str, typer.Option(help="Completed SEC index date, YYYY-MM-DD.")],
    max_filings: Annotated[int, typer.Option(min=1, max=5000)] = 250,
    cache_dir: Annotated[Path, typer.Option()] = Path("data/cache/sec-daily-index"),
    output_root: Annotated[Path, typer.Option()] = Path("data/staging/sec-daily"),
    execute: Annotated[bool, typer.Option()] = False,
) -> None:
    """Resume canonical acquisition of one global ownership-filing day."""
    from .ingestion.sec.daily_history import ingest_day

    index_day = date.fromisoformat(day)
    if not execute:
        _echo({"status": "DRY_RUN", "day": day, "maxFilings": max_filings})
        return
    source = SECDailyIndexSource(
        validate_sec_user_agent(os.getenv("SEC_USER_AGENT", "")), cache_dir=cache_dir,
    )
    try:
        report = ingest_day(source, day=index_day, output_root=output_root, max_filings=max_filings)
    finally:
        source.close()
    _echo({key: value for key, value in report.items() if key != "filings"})
    if report["status"] != "ACQUIRED":
        raise typer.Exit(1)


@app.command("acquire-sec-daily")
def acquire_sec_daily(
    repository: Annotated[str, typer.Option(help="GitHub owner/repository checkpoint store.")],
    target: Annotated[str, typer.Option(help="Full audited commit SHA for data release tags.")],
    start: Annotated[str | None, typer.Option(help="Range start, YYYY-MM-DD.")] = None,
    end: Annotated[str | None, typer.Option(help="Range end; default prior Eastern day.")] = None,
    max_days: Annotated[int, typer.Option(min=1, max=10)] = 3,
    max_filings: Annotated[int, typer.Option(min=1, max=5000)] = 750,
    output_root: Annotated[Path, typer.Option()] = Path("work/sec-acquisition"),
    execute: Annotated[bool, typer.Option()] = False,
) -> None:
    """Resume and verify durable SEC checkpoints; no scoring, cursor, Pages or alerts."""
    from zoneinfo import ZoneInfo

    from .ingestion.sec.release_store import ReleaseCheckpointStore
    from .pipeline.sec_acquisition import acquire_range

    last = date.fromisoformat(end) if end else (
        datetime.now(ZoneInfo("America/New_York")).date() - timedelta(days=1)
    )
    first = date.fromisoformat(start) if start else last - timedelta(days=6)
    store = ReleaseCheckpointStore(repository, target=target)
    if not execute:
        _echo({"status": "DRY_RUN", "start": first.isoformat(), "end": last.isoformat(),
               "repository": repository, "publishable": False, "alertsAllowed": False})
        return
    if output_root.exists():
        raise typer.BadParameter("Use a fresh output root; durable progress restores from Releases")
    source = SECDailyIndexSource(
        validate_sec_user_agent(os.getenv("SEC_USER_AGENT", "")),
        cache_dir=output_root / "raw-cache",
    )
    try:
        report = acquire_range(source, store, start=first, end=last, root=output_root,
                               max_days=max_days, max_filings=max_filings)
    finally:
        source.close()
    _echo(report)
    if report["storageStatus"] != "VERIFIED":
        raise typer.Exit(1)


@app.command("plan-live-market")
def plan_live_market_command(
    canonical: Annotated[list[Path], typer.Option("--canonical")],
    sec_batch: Annotated[Path, typer.Option()],
    identities: Annotated[Path, typer.Option()],
    as_of: Annotated[str, typer.Option()],
    output_dir: Annotated[Path, typer.Option()] = Path("data/staging/market-plan"),
) -> None:
    """Write PIT symbol/benchmark lists for update-market, without network access."""
    from .pipeline.live_inputs import plan_live_market

    report = plan_live_market(
        canonical_sources=canonical, sec_envelope=sec_batch, identity_rows=identities,
        as_of=datetime.fromisoformat(as_of),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in ("symbols", "benchmarks"):
        path = output_dir / f"{name}.txt"
        temporary = path.with_suffix(".txt.tmp")
        temporary.write_text("\n".join(report[name]) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    _write_json(output_dir / "plan.json", report)
    _echo(report)


@app.command("prepare-live-inputs")
def prepare_live_inputs_command(
    canonical: Annotated[list[Path], typer.Option("--canonical")],
    sec_batch: Annotated[Path, typer.Option()],
    identities: Annotated[Path, typer.Option()],
    prior_state: Annotated[Path, typer.Option()],
    market_bars: Annotated[Path, typer.Option()],
    market_quality: Annotated[Path, typer.Option()],
    as_of: Annotated[str, typer.Option()],
    run_id: Annotated[str, typer.Option()],
    work_root: Annotated[Path, typer.Option()] = Path("work/live-daily"),
    core_coverage: PathOption = None,
    backtest_report: PathOption = None,
) -> None:
    """Connect verified SEC/market artifacts to daily --execute --input-manifest."""
    from .pipeline.live_inputs import prepare_live_inputs

    result = prepare_live_inputs(
        canonical_sources=canonical, sec_envelope=sec_batch, identity_rows=identities,
        prior_state_file=prior_state, market_bars_file=market_bars,
        market_quality_file=market_quality, core_coverage_file=core_coverage,
        backtest_report_file=backtest_report, as_of=datetime.fromisoformat(as_of),
        run_id=run_id, work_root=work_root,
    )
    _echo({"status": "PREPARED", "manifest": str(result.manifest_path),
           "symbols": result.symbols, "benchmarks": result.benchmarks})


@app.command("update-market")
def update_market(
    csv_path: PathOption = None,
    symbols_file: PathOption = None,
    benchmark_file: PathOption = None,
    cache_dir: Annotated[Path, typer.Option()] = Path("data/cache/market"),
    shard_index: Annotated[int, typer.Option(min=0)] = 0,
    shard_count: Annotated[int, typer.Option(min=1, max=3)] = 1,
    execute: Annotated[bool, typer.Option(help="Allow Stooq network requests.")] = False,
    output: Annotated[Path, typer.Option()] = Path("data/staging/market.parquet"),
    quality_output: Annotated[Path, typer.Option()] = Path("data/staging/market-quality.json"),
    as_of: Annotated[str | None, typer.Option(help="ISO date cutoff.")] = None,
) -> None:
    """Persist provider-neutral bars from CSV fallback or a bounded Stooq shard."""

    if csv_path is not None and symbols_file is not None:
        raise typer.BadParameter("choose either --csv-path or --symbols-file")
    if csv_path is None and symbols_file is None:
        _echo(
            {
                "command": "update-market",
                "status": "DRY_RUN",
                "alternatives": [["--csv-path"], ["--symbols-file", "--execute"]],
            }
        )
        return
    cutoff = date.fromisoformat(as_of) if as_of else date.today()
    failures: dict[str, str] = {}
    benchmarks: list[str] = []
    requested: list[str]

    def symbols_from(path: Path) -> list[str]:
        values = [
            item.strip().upper()
            for item in path.read_text("utf-8").replace(",", "\n").splitlines()
            if item.strip() and not item.strip().startswith("#")
        ]
        if not values:
            raise typer.BadParameter(f"symbol file is empty: {path}")
        return list(dict.fromkeys(values))

    if csv_path is not None:
        if csv_path.suffix.lower() in {".parquet", ".pq"}:
            # A prior canonical market artifact is a valid offline fallback.
            # Normalize through the CSV provider so both paths enforce the
            # same point-in-time and economic row validation.
            frame = pl.read_parquet(csv_path)
            if "date" in frame.columns:
                frame = frame.with_columns(pl.col("date").cast(pl.Date))
            # Avoid materializing provider metadata (notably timezone-aware
            # ``available_at`` values) through Polars' Python exporter.  The
            # canonical provider reconstructs those fields deterministically.
            columns = [
                name
                for name in (
                    "date",
                    "ticker",
                    "symbol",
                    "open",
                    "high",
                    "low",
                    "close",
                    "adj_close",
                    "volume",
                    "adjusted",
                    "is_adjusted",
                    "adjustment_basis",
                    "split_factor",
                )
                if name in frame.columns
            ]
            frame = frame.select(columns)
            provider = CsvMarketDataProvider(frame.to_dicts(), as_of_date=cutoff)
            source_name = "parquet"
        else:
            provider = CsvMarketDataProvider(csv_path, as_of_date=cutoff)
            source_name = "csv"
        bars = list(provider.bars)
        requested = list(provider.symbols)
        benchmarks = symbols_from(benchmark_file) if benchmark_file is not None else []
        benchmarks = list(dict.fromkeys(["SPY", *benchmarks]))
    else:
        assert symbols_file is not None
        if not execute:
            _echo(
                {
                    "command": "update-market",
                    "status": "DRY_RUN",
                    "requires": ["--symbols-file", "--execute"],
                }
            )
            return

        requested = symbols_from(symbols_file)
        benchmarks = symbols_from(benchmark_file) if benchmark_file is not None else ["SPY"]
        benchmarks = list(dict.fromkeys(["SPY", *benchmarks]))
        source_name = "stooq"
        live = StooqMarketDataProvider(cache_dir=cache_dir)
        try:
            batch = live.fetch_shard(
                requested,
                shard_index=shard_index,
                shard_count=shard_count,
                as_of=cutoff,
            )
            fetched = dict(batch.bars)
            failures.update(batch.failures)
            for benchmark in benchmarks:
                try:
                    fetched[benchmark] = live.get_daily_bars(benchmark, as_of=cutoff)
                except (RuntimeError, ValueError) as exc:
                    failures[benchmark] = str(exc)
            bars = [bar for symbol in sorted(fetched) for bar in fetched[symbol]]
            requested = [
                symbol
                for index, symbol in enumerate(sorted(set(requested)))
                if index % shard_count == shard_index
            ]
        finally:
            live.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_suffix(output.suffix + ".tmp")
    pl.DataFrame([asdict(bar) for bar in bars]).write_parquet(temporary_output)
    os.replace(temporary_output, output)
    by_symbol: dict[str, list[Any]] = {}
    for bar in bars:
        by_symbol.setdefault(bar.symbol, []).append(bar)
    report = probe_market_coverage(bars, requested, as_of=cutoff)
    successful = list(report.covered_symbols)
    coverage = report.coverage_rate
    latest_session = max(
        (bar.date for symbol in successful for bar in by_symbol[symbol]),
        default=None,
    )
    benchmark_evidence: dict[str, dict[str, Any]] = {}
    for symbol in benchmarks:
        symbol_bars = by_symbol.get(symbol, [])
        latest = max((bar.date for bar in symbol_bars if bar.date <= cutoff), default=None)
        age_days = (cutoff - latest).days if latest is not None else None
        fresh = bool(
            symbol_bars
            and latest is not None
            and latest_session is not None
            and latest >= latest_session
            and age_days is not None
            and age_days <= 3
        )
        benchmark_evidence[symbol] = {
            "covered": bool(symbol_bars),
            "latestSession": latest.isoformat() if latest else None,
            "ageDays": age_days,
            "fresh": fresh,
            "rows": len(symbol_bars),
        }
    benchmark_fresh = all(item["fresh"] for item in benchmark_evidence.values())
    quality_flags = {
        symbol: list(report.reasons.get(symbol, ("covered",)))
        for symbol in report.requested_symbols
    }
    for symbol, evidence in benchmark_evidence.items():
        if not evidence["covered"]:
            quality_flags[symbol] = ["missing_benchmark"]
        elif not evidence["fresh"]:
            quality_flags[symbol] = ["stale_benchmark"]
    quality = {
        "schemaVersion": "1.0.0",
        "source": source_name,
        "asOf": cutoff.isoformat(),
        "requestedSymbols": len(requested),
        "requestedSymbolNames": list(report.requested_symbols),
        "successfulSymbols": len(successful),
        "coverageNumerator": len(successful),
        "coverageDenominator": len(requested),
        "coverage": round(coverage, 6),
        "coveragePass": bool(requested) and report.is_acceptable,
        "quarantinedSymbols": list(report.quarantined_symbols),
        "staleSymbols": list(report.stale_symbols),
        "qualityFlags": quality_flags,
        "benchmarks": benchmarks,
        "benchmarkCoverage": {
            "covered": sum(1 for item in benchmark_evidence.values() if item["covered"]),
            "requested": len(benchmark_evidence),
        },
        "benchmarkEvidence": benchmark_evidence,
        "benchmarkFresh": benchmark_fresh,
        "latestSession": latest_session.isoformat() if latest_session else None,
        "failures": failures,
        "provenance": {
            "provider": source_name,
            "asOf": cutoff.isoformat(),
            "barCount": len(bars),
        },
    }
    _write_json(quality_output, quality)
    status = "SUCCEEDED" if quality["coveragePass"] and benchmark_fresh else "DEGRADED"
    _echo(
        {
            "command": "update-market",
            "status": status,
            "symbols": len(successful),
            "bars": len(bars),
            "output": str(output),
            "qualityOutput": str(quality_output),
        }
    )


@app.command("build-features")
def build_features(
    market: PathOption = None,
    output: Annotated[Path, typer.Option()] = Path("data/warehouse/price-features.parquet"),
    as_of: Annotated[str | None, typer.Option(help="ISO date cutoff.")] = None,
) -> None:
    """Build bounded price/state facts from canonical market bars."""

    if market is None:
        _echo({"command": "build-features", "status": "DRY_RUN", "requires": ["--market"]})
        return
    cutoff = date.fromisoformat(as_of) if as_of else date.today()
    features = price_features(pl.read_parquet(market), as_of=cutoff)
    output.parent.mkdir(parents=True, exist_ok=True)
    features.write_parquet(output)
    _echo({"command": "build-features", "status": "SUCCEEDED", "rows": features.height})


@app.command("build-signals")
def build_signals(
    components: PathOption = None,
    output: Annotated[Path, typer.Option()] = Path("data/warehouse/scores.json"),
) -> None:
    """Apply frozen score weights to a JSON mapping of model components."""

    if components is None:
        _echo({"command": "build-signals", "status": "DRY_RUN", "requires": ["--components"]})
        return
    raw = json.loads(components.read_text("utf-8"))
    if not isinstance(raw, dict):
        raise typer.BadParameter("components must be a JSON object keyed by model name")
    if any(not isinstance(values, dict) for values in raw.values()):
        raise typer.BadParameter("every component model must contain a JSON object")
    engine = ScoreEngine()
    results = {name: asdict(engine.score(name, values)) for name, values in raw.items()}
    _write_json(output, results)
    _echo({"command": "build-signals", "status": "SUCCEEDED", "output": str(output)})


@app.command("backtest")
def backtest(
    events: PathOption = None,
    bars: PathOption = None,
    validation_evidence: Annotated[
        Path | None,
        typer.Option(
            help="JSON validation attestation; omitted evidence can never produce a PASS gate."
        ),
    ] = None,
    evaluation_stage: Annotated[
        EvaluationStage,
        typer.Option(help="dev-validation never reveals sealed OOS results."),
    ] = EvaluationStage.DEV_VALIDATION,
    output: Annotated[Path, typer.Option()] = Path("data/backtest/report.json"),
) -> None:
    """Run the point-in-time event backtest after validated inputs are supplied."""

    if events is None or bars is None:
        _echo(
            {
                "command": "backtest",
                "status": "DRY_RUN",
                "requires": ["--events", "--bars"],
            }
        )
        return
    rows = json.loads(events.read_text("utf-8"))
    if not isinstance(rows, list):
        raise typer.BadParameter("events must be a JSON array")
    if any(not isinstance(row, dict) for row in rows):
        raise typer.BadParameter("every event must be a JSON object")
    evidence: dict[str, Any] | None = None
    if validation_evidence is not None:
        try:
            loaded_evidence = json.loads(validation_evidence.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise typer.BadParameter(f"validation evidence is unreadable: {exc}") from exc
        if not isinstance(loaded_evidence, dict):
            raise typer.BadParameter("validation evidence must be a JSON object")
        evidence = loaded_evidence
    signals = [
        BacktestSignal(
            signal_id=str(row["signal_id"]),
            ticker=str(row["ticker"]),
            signal_type=str(row["signal_type"]),
            score=float(row["score"]),
            accepted_at=(
                datetime.fromisoformat(str(row["accepted_at"])) if row.get("accepted_at") else None
            ),
            knowledge_at=(
                datetime.fromisoformat(str(row["knowledge_at"]))
                if row.get("knowledge_at")
                else None
            ),
            transaction_date=(
                date.fromisoformat(str(row["transaction_date"]))
                if row.get("transaction_date")
                else None
            ),
            feature_as_of=(
                datetime.fromisoformat(str(row["feature_as_of"]))
                if row.get("feature_as_of") and "T" in str(row["feature_as_of"])
                else date.fromisoformat(str(row["feature_as_of"]))
                if row.get("feature_as_of")
                else None
            ),
            feature_available_at=(
                datetime.fromisoformat(str(row["feature_available_at"]))
                if row.get("feature_available_at")
                else None
            ),
            sector=str(row["sector"]) if row.get("sector") is not None else None,
            issuer_cik=str(row["issuer_cik"]) if row.get("issuer_cik") is not None else None,
            exposure_family=(
                str(row["exposure_family"]) if row.get("exposure_family") is not None else None
            ),
            score_version=str(row.get("score_version", "scoring.v1")),
            score_config_hash=(
                str(row["score_config_hash"]) if row.get("score_config_hash") is not None else None
            ),
            score_lineage=(
                str(row["score_lineage"]) if row.get("score_lineage") is not None else None
            ),
            methodology_hash=(
                str(row["methodology_hash"]) if row.get("methodology_hash") is not None else None
            ),
            methodology_status=(
                str(row["methodology_status"])
                if row.get("methodology_status") is not None
                else None
            ),
            run_id=str(row["run_id"]) if row.get("run_id") is not None else None,
            frozen_at=(
                datetime.fromisoformat(str(row["frozen_at"])) if row.get("frozen_at") else None
            ),
        )
        for row in rows
    ]
    provider = CsvMarketDataProvider(bars, as_of_date=date.max)
    spy = provider.get_daily_bars("SPY")
    company_bars = [bar for bar in provider.bars if bar.symbol != "SPY"]
    benchmark_families = {
        "SIMPLE_PS": "simple_ps",
        "UNIQUE_BUYER_RATIO": "unique_buyer_ratio",
        "LARGEST_BUYS": "largest_buys",
        "CLUSTER_BUYS": "cluster_buys",
    }
    unknown_families = sorted(
        {
            str(signal.exposure_family)
            for signal in signals
            if signal.exposure_family not in {None, "FULL_ENGINE", *benchmark_families}
        }
    )
    if unknown_families:
        raise typer.BadParameter(
            "unsupported exposure_family values: " + ", ".join(unknown_families)
        )
    full_signals = [signal for signal in signals if signal.exposure_family in {None, "FULL_ENGINE"}]
    if not full_signals:
        raise typer.BadParameter("events must include a FULL_ENGINE exposure family")
    result = run_backtest(full_signals, bars=company_bars, spy_bars=spy)
    sealed = evaluation_stage is EvaluationStage.SEALED_OOS
    selected_period = BacktestPeriod.OOS if sealed else BacktestPeriod.VALIDATION
    oos_report = result.sealed_oos.final_report() if sealed else None
    selected_results = oos_report.results if oos_report is not None else result.validation
    benchmark_groups = {}
    benchmark_counts = {}
    for family, benchmark_name in benchmark_families.items():
        selected_signals = [signal for signal in signals if signal.exposure_family == family]
        if not selected_signals:
            continue
        benchmark_result = run_backtest(selected_signals, bars=company_bars, spy_bars=spy)
        benchmark_period = (
            benchmark_result.sealed_oos.final_report().results
            if sealed
            else benchmark_result.validation
        )
        events_for_family = benchmark_period.simple_benchmark.events
        benchmark_groups[benchmark_name] = events_for_family
        benchmark_counts[benchmark_name] = len(events_for_family)
    formal = build_backtest_report(
        oos_report if oos_report is not None else selected_results,
        period=selected_period,
        benchmark_groups=benchmark_groups,
        validation_evidence=evidence,
        evaluation_stage=evaluation_stage,
    )
    gate = formal.gate
    report = {
        "schemaVersion": "1.0.0",
        "scoreVersion": "scoring.v1",
        "evaluationStage": evaluation_stage.value,
        "status": gate.status if gate is not None else "DEVELOPMENT",
        "publicationDisposition": (
            "VALIDATED"
            if gate is not None and gate.status == "PASS"
            else "EXPERIMENTAL"
            if gate is not None and gate.status == "INCONCLUSIVE"
            else "RESEARCH_ONLY"
        ),
        "alertsDefaultEnabled": gate is not None and gate.status == "PASS",
        "developmentEvents": len(result.development.simple_benchmark.events),
        "validationEvents": len(result.validation.simple_benchmark.events),
        "oosEvents": len(oos_report.results.simple_benchmark.events) if oos_report else None,
        "benchmarkEvents": benchmark_counts,
        "formalReport": asdict(formal),
        "attrition": asdict(oos_report.attrition) if oos_report else asdict(result.attrition),
        "caveats": [asdict(item) for item in formal.caveats],
        "duplicateSignalIds": list(result.duplicate_signal_ids),
        "sealedOosAccess": [purpose.value for purpose in result.sealed_oos.access_log],
    }
    _write_json(output, report)
    _echo({"command": "backtest", "status": "SUCCEEDED", "output": str(output)})


@app.command("export-dashboard")
def export_dashboard(
    source: PathOption = None,
    output: Annotated[Path, typer.Option()] = Path("app/public/data"),
) -> None:
    """Validate and atomically replace compact browser JSON artifacts."""

    if source is None:
        _echo({"command": "export-dashboard", "status": "DRY_RUN", "requires": ["--source"]})
        return
    raw = json.loads(source.read_text("utf-8"))
    result = publish_dashboard(raw, output, chunk_by_ticker=True)
    _echo(
        {
            "command": "export-dashboard",
            "status": "SUCCEEDED",
            "manifest": str(result.manifest_path),
        }
    )


@app.command("send-alerts")
def send_alerts(
    candidates: PathOption = None,
    execute: Annotated[bool, typer.Option(help="Enable external delivery.")] = False,
    outbox: Annotated[Path, typer.Option()] = Path("data/state/alerts.sqlite"),
    manifest: PathOption = None,
    channel: Annotated[str, typer.Option(help="telegram, email, or all")] = "all",
    policy_path: Annotated[Path, typer.Option("--policy")] = Path(
        "config/notifications.v1.yaml"
    ),
) -> None:
    """Preview alert delivery unless external sending is explicitly enabled."""

    if candidates is None:
        _echo(
            {
                "command": "send-alerts",
                "status": "DRY_RUN",
                "requires": ["--candidates"],
                "qualityGated": True,
            }
        )
        return
    try:
        policy = load_notification_policy(policy_path)
    except NotificationPolicyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    selected_names = _channel_names(channel, policy)
    raw = json.loads(candidates.read_text("utf-8"))
    if not isinstance(raw, list):
        raise typer.BadParameter("candidates must be a JSON array")
    if any(not isinstance(row, dict) for row in raw):
        raise typer.BadParameter("every candidate must be a JSON object")
    if execute:
        if manifest is None:
            raise typer.BadParameter("--manifest is required for external delivery")
        expected_manifest = manifest.parent / "manifest.json"
        if manifest.resolve() != expected_manifest.resolve():
            raise typer.BadParameter("--manifest must name the publication manifest.json")
        try:
            publication = validate_dashboard_directory(manifest.parent)
        except DashboardExportError as exc:
            raise typer.BadParameter(f"publication manifest is invalid: {exc}") from exc
        quality = publication.get("quality", {})
        if publication.get("status") != "SUCCEEDED" or quality.get("disposition") != "PASS":
            raise typer.BadParameter("external delivery requires a PASS publication manifest")
        run_id = str(publication["runId"])
        mismatched = [
            index
            for index, row in enumerate(raw)
            if not isinstance(row, dict) or str(row.get("runId", row.get("run_id", ""))) != run_id
        ]
        if mismatched:
            raise typer.BadParameter("every alert candidate must reference the PASS manifest runId")
    point = datetime.now(UTC)
    alerts = []
    for row in raw:
        candidate = AlertCandidate.from_mapping(row)
        policy_reasons = policy.suppression_reasons(candidate, at=point)
        alerts.append(
            replace(
                candidate,
                suppression_reasons=tuple(
                    dict.fromkeys((*candidate.suppression_reasons, *policy_reasons))
                ),
            )
        )
    if not execute:
        # Preview is deliberately side-effect free with respect to providers,
        # but candidates still belong in the durable audit ledger so a run
        # without Telegram credentials does not silently discard them.
        outbox.parent.mkdir(parents=True, exist_ok=True)
        ledger = SQLiteOutbox(outbox, cooldown_days=policy.cooldown_days)
        try:
            for item in alerts:
                ledger.put_candidate(item)
        finally:
            ledger.close()
        _echo(
            {
                "command": "send-alerts",
                "status": "DRY_RUN",
                "previews": [format_plain(item) for item in alerts],
                "channels": list(selected_names),
                "qualityGated": True,
            }
        )
        return
    if not policy.delivery_enabled:
        raise typer.BadParameter("external delivery is disabled by notification policy")
    channels = _configured_channels(selected_names)
    outbox.parent.mkdir(parents=True, exist_ok=True)
    ledger = SQLiteOutbox(outbox, cooldown_days=policy.cooldown_days)
    try:
        if ledger.recovered_path is not None:
            _echo(
                {
                    "command": "send-alerts",
                    "status": "BLOCKED",
                    "reason": "OUTBOX_CORRUPTION_RECOVERED",
                    "recoveryEvidence": str(ledger.recovered_path),
                }
            )
            raise typer.Exit(code=1)
        statuses = [
            {
                "candidate": item.idempotency_key,
                "channel": configured.name,
                "status": ledger.deliver(item, configured, at=point).value,
            }
            for item in alerts
            for configured in channels
        ]
    finally:
        ledger.close()
    failed = any(item["status"] in {"FAILED", "UNCERTAIN"} for item in statuses)
    _echo({"command": "send-alerts", "status": "FAILED" if failed else "SUCCEEDED",
           "deliveries": statuses})
    if failed:
        raise typer.Exit(code=1)


@app.command("test-alert-delivery")
def test_alert_delivery(
    channel: Annotated[str, typer.Option(help="telegram, email, or all")] = "all",
    execute: Annotated[bool, typer.Option(help="Send a clearly labeled test message.")] = False,
    outbox: Annotated[Path, typer.Option()] = Path("data/state/alerts.sqlite"),
    prepare: Annotated[bool, typer.Option(help="Persist a test intent without sending.")] = False,
    test_id: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Preview or explicitly send a delivery test outside signal cooldown state."""

    selected_names = _channel_names(channel)
    if prepare and (execute or not test_id):
        raise typer.BadParameter("--prepare requires --test-id and forbids --execute")
    if prepare:
        outbox.parent.mkdir(parents=True, exist_ok=True)
        ledger = SQLiteOutbox(outbox)
        try:
            for name in selected_names:
                ledger.prepare_delivery_test(str(test_id), name)
        finally:
            ledger.close()
        _echo({"command": "test-alert-delivery", "status": "PREPARED"})
        return
    point = datetime.now(UTC)
    candidate = AlertCandidate(
        issuer_cik="0000000000",
        alert_type=AlertType.TURNING,
        trigger_snapshot_id=f"test_{point:%Y%m%dT%H%M%S%fZ}",
        score=0,
        severity=Severity.INFO,
        ticker="TEST",
        state="FALLING",
        reasons=("DELIVERY_TEST_ONLY", "NO_MARKET_SIGNAL"),
        created_at=point,
    )
    if not execute:
        previews = {
            "telegram": preview_telegram_html(candidate).text,
            "email": preview_email_html(candidate).alternative_text,
        }
        _echo(
            {
                "command": "test-alert-delivery",
                "status": "DRY_RUN",
                "channels": list(selected_names),
                "previews": {name: previews[name] for name in selected_names},
            }
        )
        return
    channels = _configured_channels(selected_names)
    outbox.parent.mkdir(parents=True, exist_ok=True)
    ledger = SQLiteOutbox(outbox)
    results: list[dict[str, str | None]] = []
    failed = False
    try:
        for configured in channels:
            if test_id is not None and not ledger.claim_delivery_test(test_id, configured.name):
                raise typer.BadParameter("test was not prepared or was already attempted")
            preview = configured.preview(candidate)
            result = configured.send(preview)
            configured.record_result(candidate, result)
            ledger.record_delivery_test(configured.name, result, at=point, test_id=test_id)
            results.append(
                {
                    "channel": configured.name,
                    "status": result.status.value,
                    "providerId": result.provider_id,
                    "error": result.error,
                }
            )
            failed = failed or result.status.value != "SENT"
    finally:
        ledger.close()
    _echo(
        {
            "command": "test-alert-delivery",
            "status": "FAILED" if failed else "SUCCEEDED",
            "deliveries": results,
        }
    )
    if failed:
        raise typer.Exit(code=1)


@app.command("export-settings-status")
def export_settings_status(
    manifest: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()] = Path("data/settings-status.json"),
    outbox: Annotated[Path, typer.Option()] = Path("data/state/alerts.sqlite"),
    policy_path: Annotated[Path, typer.Option("--policy")] = Path(
        "config/notifications.v1.yaml"
    ),
    environment: Annotated[str, typer.Option()] = "production",
) -> None:
    """Export a public settings projection without exposing credential values."""

    try:
        publication = validate_dashboard_directory(manifest.parent)
        _, alerts_allowed = dashboard_publication_policy(publication)
        policy = load_notification_policy(policy_path)
    except (DashboardExportError, NotificationPolicyError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    reasons = list(publication["quality"]["issues"])
    if not policy.delivery_enabled:
        reasons.append("DELIVERY_DISABLED_BY_POLICY")
    outbox.parent.mkdir(parents=True, exist_ok=True)
    ledger = SQLiteOutbox(outbox, cooldown_days=policy.cooldown_days)
    try:
        delivery_history = [dict(row) for row in ledger.history()]
        test_history = [dict(row) for row in ledger.test_history()]
        if ledger.recovered_path is not None:
            reasons.append("OUTBOX_CORRUPTION_RECOVERED")
    finally:
        ledger.close()
    status = build_settings_status(
        policy,
        environment=environment,
        alerts_allowed=alerts_allowed and policy.delivery_enabled,
        blocking_reasons=reasons,
        secrets=os.environ,
        delivery_history=delivery_history,
        test_history=test_history,
    )
    _write_json(output, status)
    _echo({"command": "export-settings-status", "status": "SUCCEEDED", "output": str(output)})


@app.command("daily")
def daily(
    fixture_only: Annotated[bool, typer.Option(help="Run without network or alerts.")] = False,
    execute: Annotated[bool, typer.Option(help="Execute a validated input manifest.")] = False,
    input_manifest: PathOption = None,
) -> None:
    """Run a safe fixture validation or report the scheduled production plan."""

    if fixture_only and execute:
        raise typer.BadParameter("--fixture-only and --execute are mutually exclusive")
    if input_manifest is not None and not execute:
        raise typer.BadParameter("--input-manifest requires --execute")
    started = datetime.now(UTC)
    if fixture_only:
        fixture_root = Path("tests/fixtures")
        xml_files = sorted(fixture_root.glob("form*.xml"))
        records = 0
        quarantines = 0
        observed = datetime.now(UTC)
        for index, path in enumerate(xml_files, start=1):
            parsed = parse_sec_filing(
                path.read_bytes(),
                {
                    "accession_number": f"0001234567-26-{index:06d}",
                    "source_url": ("https://www.sec.gov/Archives/edgar/data/fixture/" + path.name),
                    "accepted_at": observed,
                    "observed_at": observed,
                    "run_id": "run_fixture_daily_20260830",
                },
            )
            records += len(parsed.records)
            quarantines += len(parsed.quarantines)
        market = CsvMarketDataProvider(fixture_root / "daily_market.csv", as_of_date=date.max)
        status = "SUCCEEDED" if records else "FAILED"
        _echo(
            {
                "command": "daily",
                "status": status,
                "mode": "fixture-only",
                "startedAt": started.isoformat(),
                "secRecords": records,
                "quarantines": quarantines,
                "marketBars": len(market.bars),
            }
        )
        if status != "SUCCEEDED":
            raise typer.Exit(1)
        return
    if execute:
        if input_manifest is None:
            raise typer.BadParameter("--input-manifest is required with --execute")
        from .domain.daily_manifest import load_daily_input_manifest

        try:
            load_daily_input_manifest(input_manifest)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--input-manifest") from exc
        pipeline = import_module("insider_turning_engine.pipeline.daily")
        run_daily_pipeline = cast(Any, pipeline.run_daily_pipeline)
        result = run_daily_pipeline(input_manifest)
        mapping = result.as_mapping() if hasattr(result, "as_mapping") else result
        if not isinstance(mapping, dict):
            raise typer.BadParameter("daily pipeline result must map to a JSON object")
        _echo({"command": "daily", **mapping})
        return
    _echo(
        {
            "command": "daily",
            "status": "DRY_RUN",
            "requires": ["SEC_USER_AGENT", "validated market coverage", "publish quality gates"],
        }
    )
