"""Command-line entry points for reproducible local and scheduled runs."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any

import httpx
import polars as pl
import typer

from .backtest import BacktestSignal, build_backtest_report, run_backtest
from .export.dashboard import export_dashboard as publish_dashboard
from .features.price import price_features
from .ingestion.market import CsvMarketDataProvider
from .ingestion.sec import (
    SECIncrementalSource,
    SecRawRecord,
    decode_cursor,
    parse_sec_filing,
    stage_quarter,
    validate_sec_user_agent,
)
from .notifications import AlertCandidate, SQLiteOutbox, TelegramHTTPChannel, format_plain
from .scoring import ScoreEngine

app = typer.Typer(
    name="insider-turning",
    help="Build point-in-time insider-turning research snapshots.",
    no_args_is_help=True,
    add_completion=False,
)

PathOption = Annotated[Path | None, typer.Option()]


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


@app.command("update-sec")
def update_sec(
    xml: PathOption = None,
    accession: Annotated[str | None, typer.Option()] = None,
    source_url: Annotated[str | None, typer.Option()] = None,
    accepted_at: Annotated[str | None, typer.Option(help="ISO SEC acceptance timestamp.")] = None,
    cik_file: PathOption = None,
    since: Annotated[str | None, typer.Option()] = None,
    through: Annotated[str | None, typer.Option()] = None,
    cursor_file: Annotated[Path, typer.Option()] = Path("data/state/sec.cursor"),
    execute: Annotated[bool, typer.Option(help="Allow SEC network requests.")] = False,
    output: Annotated[Path, typer.Option()] = Path("data/staging/sec-incremental.json"),
) -> None:
    """Normalize one fetched ownership XML; scheduled runs use the incremental adapter."""

    if xml is None and (cik_file is None or not execute):
        _echo(
            {
                "command": "update-sec",
                "status": "DRY_RUN",
                "alternatives": [
                    ["--xml", "--accession", "--source-url"],
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
    if xml is not None:
        if accession is None or source_url is None:
            raise typer.BadParameter("--accession and --source-url are required with --xml")
        accepted = datetime.fromisoformat(accepted_at) if accepted_at else datetime.now(UTC)
        result = parse_sec_filing(
            xml.read_bytes(),
            {
                "accession_number": accession,
                "source_url": source_url,
                "accepted_at": accepted,
                "observed_at": datetime.now(UTC),
                "run_id": "run_cli_incremental_20260830",
            },
        )
        records.extend(record.canonical_dump() for record in result.records)
        quarantines.extend(item.model_dump(mode="json") for item in result.quarantines)
    else:
        assert cik_file is not None
        user_agent = os.getenv("SEC_USER_AGENT", "").strip()
        try:
            user_agent = validate_sec_user_agent(user_agent)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        cik_text = cik_file.read_text("utf-8")
        ciks = [item.strip() for item in cik_text.replace(",", "\n").splitlines() if item.strip()]
        source = SECIncrementalSource(
            ciks,
            user_agent,
            cache_dir="data/cache/sec-incremental",
            run_id="run_cli_incremental_20260830",
        )
        cursor, recovered_cursor = _recover_cursor(cursor_file)
        page = source.fetch(cursor, through, since=since)
        next_cursor = page.next_cursor
        quarantines.extend(item.model_dump(mode="json") for item in page.quarantines)
        for reference in page.records:
            fetched = source.get(reference.provider_record_id)
            if isinstance(fetched, SecRawRecord):
                parsed = source.normalize(fetched)
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
    if xml is None and not incomplete and next_cursor and next_cursor != cursor:
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
            "cursorRecovered": str(recovered_cursor) if xml is None and recovered_cursor else None,
            "cursorAdvanced": cursor_advanced,
        }
    )
    if incomplete:
        raise typer.Exit(1)


@app.command("update-market")
def update_market(
    csv_path: PathOption = None,
    output: Annotated[Path, typer.Option()] = Path("data/staging/market.parquet"),
    as_of: Annotated[str | None, typer.Option(help="ISO date cutoff.")] = None,
) -> None:
    """Validate the canonical CSV fallback and persist provider-neutral bars."""

    if csv_path is None:
        _echo({"command": "update-market", "status": "DRY_RUN", "requires": ["--csv-path"]})
        return
    cutoff = date.fromisoformat(as_of) if as_of else date.today()
    provider = CsvMarketDataProvider(csv_path, as_of_date=cutoff)
    output.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame([asdict(bar) for bar in provider.bars]).write_parquet(output)
    _echo(
        {
            "command": "update-market",
            "status": "SUCCEEDED",
            "symbols": len(provider.symbols),
            "bars": len(provider.bars),
            "output": str(output),
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
    engine = ScoreEngine()
    results = {
        name: asdict(engine.score(name, values))
        for name, values in raw.items()
        if isinstance(values, dict)
    }
    _write_json(output, results)
    _echo({"command": "build-signals", "status": "SUCCEEDED", "output": str(output)})


@app.command("backtest")
def backtest(
    events: PathOption = None,
    bars: PathOption = None,
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
            frozen_at=(
                datetime.fromisoformat(str(row["frozen_at"])) if row.get("frozen_at") else None
            ),
        )
        for row in rows
        if isinstance(row, dict)
    ]
    provider = CsvMarketDataProvider(bars, as_of_date=date.max)
    spy = provider.get_daily_bars("SPY")
    company_bars = [bar for bar in provider.bars if bar.symbol != "SPY"]
    result = run_backtest(signals, bars=company_bars, spy_bars=spy)
    oos = result.sealed_oos.final_report()
    formal = build_backtest_report(oos)
    gate = formal.gate
    report = {
        "schemaVersion": "1.0.0",
        "scoreVersion": "scoring.v1",
        "status": gate.status if gate is not None else "INCONCLUSIVE",
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
        "oosEvents": len(oos.results.simple_benchmark.events),
        "formalReport": asdict(formal),
        "attrition": asdict(oos.attrition),
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
    raw = json.loads(candidates.read_text("utf-8"))
    if not isinstance(raw, list):
        raise typer.BadParameter("candidates must be a JSON array")
    alerts = [AlertCandidate.from_mapping(row) for row in raw if isinstance(row, dict)]
    if not execute:
        # Preview is deliberately side-effect free with respect to providers,
        # but candidates still belong in the durable audit ledger so a run
        # without Telegram credentials does not silently discard them.
        outbox.parent.mkdir(parents=True, exist_ok=True)
        ledger = SQLiteOutbox(outbox)
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
                "qualityGated": True,
            }
        )
        return
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise typer.BadParameter("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")

    def transport(url: str, payload: Any) -> httpx.Response:
        return httpx.post(url, data=payload, timeout=20.0)

    outbox.parent.mkdir(parents=True, exist_ok=True)
    ledger = SQLiteOutbox(outbox)
    channel = TelegramHTTPChannel(token, chat_id, transport)
    try:
        statuses = [ledger.deliver(item, channel).value for item in alerts]
    finally:
        ledger.close()
    _echo({"command": "send-alerts", "status": "SUCCEEDED", "deliveries": statuses})


@app.command("daily")
def daily(
    fixture_only: Annotated[bool, typer.Option(help="Run without network or alerts.")] = False,
) -> None:
    """Run a safe fixture validation or report the scheduled production plan."""

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
    _echo(
        {
            "command": "daily",
            "status": "DRY_RUN",
            "requires": ["SEC_USER_AGENT", "validated market coverage", "publish quality gates"],
        }
    )
