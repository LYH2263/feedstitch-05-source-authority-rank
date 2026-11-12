from __future__ import annotations

from typing import Any

from app.config import FIXTURES_DIR
from app.db import connect
from app.engines.merge_rules import decide_merge, eligible_for_incremental
from app.engines.parse_feed import parse_fixture
from app.modules.source_authority_rank import conflict_reason
from app.repositories import canonical as canon_repo
from app.repositories import runs as runs_repo
from app.repositories import sources as sources_repo


def preview_source(source_id: int) -> dict[str, Any]:
    conn = connect()
    try:
        source = sources_repo.get_source(conn, source_id)
        if not source:
            raise ValueError("source not found")
        path = FIXTURES_DIR / source["fixture_path"]
        items = parse_fixture(path, source["format"])
        return {
            "source": source,
            "count": len(items),
            "items": items[:50],
        }
    finally:
        conn.close()


def run_ingest(source_id: int, mode: str = "incremental") -> dict[str, Any]:
    if mode not in ("incremental", "full"):
        raise ValueError("mode must be incremental or full")

    conn = connect()
    try:
        source = sources_repo.get_source(conn, source_id)
        if not source:
            raise ValueError("source not found")
        if not source["enabled"]:
            raise ValueError("source disabled")

        if mode == "full":
            sources_repo.set_watermark(conn, source_id, None)
            source["watermark_ts"] = None

        run_id = runs_repo.create_run(conn, source_id, mode)
        path = FIXTURES_DIR / source["fixture_path"]

        try:
            items = parse_fixture(path, source["format"])
        except Exception as exc:  # noqa: BLE001
            runs_repo.finish_run(
                conn,
                run_id,
                status="failed",
                parsed=0,
                upserted=0,
                conflicts=0,
                authority_isolated=0,
                skipped=0,
                report={"error": str(exc)},
            )
            conn.commit()
            raise

        parsed = 0
        counters: dict[str, int] = {
            "insert": 0,
            "upsert": 0,
            "authority_override": 0,
            "conflict": 0,
            "authority_lost": 0,
            "skip_stale": 0,
            "skipped_watermark": 0,
        }
        dispositions: list[str] = []
        max_event_ts: str | None = source.get("watermark_ts")
        incoming_rank = int(source.get("authority_rank") or 0)

        def observe_event(ts: str) -> None:
            nonlocal max_event_ts
            if max_event_ts is None or ts > max_event_ts:
                max_event_ts = ts

        for item in items:
            parsed += 1
            if mode == "incremental" and not eligible_for_incremental(
                item["event_ts"],
                source.get("watermark_ts"),
                int(source.get("lookback_seconds") or 0),
            ):
                runs_repo.insert_staging(
                    conn,
                    run_id=run_id,
                    source_id=source_id,
                    item=item,
                    disposition="skipped_watermark",
                )
                counters["skipped_watermark"] += 1
                dispositions.append("skipped_watermark")
                continue

            existing = canon_repo.get_by_key(conn, item["business_key"])
            existing_view = None
            owner_rank: int | None = None
            owner_source_id: int | None = None

            if existing:
                owner_source_id = int(existing["source_id"])
                owner = sources_repo.get_source(conn, owner_source_id)
                if owner is not None:
                    owner_rank = int(owner.get("authority_rank") or 0)
                existing_view = {
                    "business_key": existing["business_key"],
                    "title": existing["title"],
                    "price": existing["price"],
                    "category": existing["category"],
                    "event_ts": existing["event_ts"],
                    "source_revision": existing["source_revision"],
                    "payload": existing["payload"],
                }

            decision = decide_merge(
                existing_view,
                item,
                incoming_authority=incoming_rank,
                owner_authority=owner_rank,
            )
            # Non-key fields do not diverge → authority is irrelevant.
            if decision not in ("authority_override", "authority_lost", "conflict"):
                owner_rank = None

            if decision in ("insert", "upsert", "authority_override"):
                if decision == "authority_override":
                    runs_repo.insert_authority_change(
                        conn,
                        run_id=run_id,
                        source_id=source_id,
                        business_key=item["business_key"],
                        previous_source_id=owner_source_id,
                        previous_authority_rank=owner_rank,
                        incoming_authority_rank=incoming_rank,
                        previous_payload=existing_view["payload"],
                        incoming_payload=item["payload"],
                    )
                canon_repo.upsert_item(conn, item, source_id)
                runs_repo.insert_staging(
                    conn,
                    run_id=run_id,
                    source_id=source_id,
                    item=item,
                    disposition=decision,
                )
                counters[decision] += 1
                dispositions.append(decision)
                observe_event(item["event_ts"])

            elif decision in ("authority_lost", "conflict"):
                reason = conflict_reason(incoming_rank, owner_rank, decision)
                runs_repo.insert_conflict(
                    conn,
                    run_id=run_id,
                    source_id=source_id,
                    business_key=item["business_key"],
                    existing_payload=existing_view["payload"] if existing_view else {},
                    incoming_payload=item["payload"],
                    reason=reason,
                    owner_source_id=owner_source_id,
                    owner_authority_rank=owner_rank,
                    incoming_authority_rank=incoming_rank,
                )
                runs_repo.insert_staging(
                    conn,
                    run_id=run_id,
                    source_id=source_id,
                    item=item,
                    disposition=decision,
                )
                counters[decision] += 1
                dispositions.append(decision)
                observe_event(item["event_ts"])

            else:
                runs_repo.insert_staging(
                    conn,
                    run_id=run_id,
                    source_id=source_id,
                    item=item,
                    disposition="skip_stale",
                )
                counters["skip_stale"] += 1
                dispositions.append("skip_stale")
                observe_event(item["event_ts"])

        if max_event_ts:
            sources_repo.set_watermark(conn, source_id, max_event_ts)

        upserted = (
            counters["insert"] + counters["upsert"] + counters["authority_override"]
        )
        conflicts = counters["conflict"]
        authority_isolated = counters["authority_lost"]
        skipped = counters["skip_stale"] + counters["skipped_watermark"]

        canonical_count = canon_repo.count_items(conn)
        staging_rows = runs_repo.count_staging(conn, run_id)
        conflict_rows = runs_repo.count_conflicts(conn, run_id)
        authority_change_rows = runs_repo.count_authority_changes(conn, run_id)

        disposition_counts = dict(counters)
        report = {
            "source_id": source_id,
            "source_name": source["name"],
            "source_authority_rank": incoming_rank,
            "mode": mode,
            "parsed_count": parsed,
            "upserted_count": upserted,
            "written_count": upserted,
            "inserted_count": counters["insert"],
            "updated_count": counters["upsert"],
            "authority_override_count": counters["authority_override"],
            "conflict_count": conflicts,
            "authority_isolated_count": authority_isolated,
            "quarantine_count": conflicts + authority_isolated,
            "skipped_count": skipped,
            "skipped_watermark_count": counters["skipped_watermark"],
            "stale_count": counters["skip_stale"],
            "canonical_count": canonical_count,
            "authority_change_count": authority_change_rows,
            "staging_rows_count": staging_rows,
            "conflict_rows_count": conflict_rows,
            "watermark_ts": max_event_ts,
            "dispositions": dispositions,
            "disposition_counts": disposition_counts,
            "reconcile": {
                "parsed_equals_dispositions": parsed == sum(disposition_counts.values()),
                "writes_equals_breakdown": upserted
                == counters["insert"]
                + counters["upsert"]
                + counters["authority_override"],
                "staging_rows_equal_parsed": staging_rows == parsed,
                "conflict_rows_equal_quarantine": conflict_rows
                == conflicts + authority_isolated,
                "authority_changes_equal_overrides": authority_change_rows
                == counters["authority_override"],
            },
        }
        runs_repo.finish_run(
            conn,
            run_id,
            status="ok",
            parsed=parsed,
            upserted=upserted,
            conflicts=conflicts,
            authority_isolated=authority_isolated,
            skipped=skipped,
            report=report,
        )
        conn.commit()
        run = runs_repo.get_run(conn, run_id)
        return run or report
    finally:
        conn.close()


def dashboard_stats() -> dict[str, Any]:
    conn = connect()
    try:
        sources = sources_repo.list_sources(conn)
        return {
            "source_count": len(sources),
            "enabled_sources": sum(1 for s in sources if s["enabled"]),
            "canonical_count": canon_repo.count_items(conn),
            "conflict_count": conn.execute("SELECT COUNT(*) c FROM conflicts").fetchone()["c"],
            "authority_isolated_count": conn.execute(
                "SELECT COUNT(*) c FROM conflicts WHERE reason = 'authority_lost'"
            ).fetchone()["c"],
            "authority_change_count": conn.execute(
                "SELECT COUNT(*) c FROM authority_changes"
            ).fetchone()["c"],
            "run_count": conn.execute("SELECT COUNT(*) c FROM runs").fetchone()["c"],
            "staging_count": conn.execute("SELECT COUNT(*) c FROM staging_rows").fetchone()["c"],
        }
    finally:
        conn.close()
