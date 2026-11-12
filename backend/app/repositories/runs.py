from __future__ import annotations

import json
import sqlite3
from typing import Any


def create_run(
    conn: sqlite3.Connection,
    source_id: int,
    mode: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO runs(source_id, mode, status, parsed_count, upserted_count,
                         conflict_count, authority_isolated_count, skipped_count,
                         report_json, created_at)
        VALUES (?,?, 'running', 0, 0, 0, 0, 0, '{}', datetime('now'))
        """,
        (source_id, mode),
    )
    return int(cur.lastrowid)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    parsed: int,
    upserted: int,
    conflicts: int,
    authority_isolated: int = 0,
    skipped: int,
    report: dict[str, Any],
) -> None:
    conn.execute(
        """
        UPDATE runs SET status=?, parsed_count=?, upserted_count=?, conflict_count=?,
            authority_isolated_count=?, skipped_count=?, report_json=? WHERE id=?
        """,
        (
            status,
            parsed,
            upserted,
            conflicts,
            authority_isolated,
            skipped,
            json.dumps(report, ensure_ascii=False),
            run_id,
        ),
    )


_RUN_SELECT = """
    SELECT r.id, r.source_id, s.name AS source_name, r.mode, r.status,
           r.parsed_count, r.upserted_count, r.conflict_count,
           r.authority_isolated_count, r.skipped_count,
           r.report_json, r.created_at
    FROM runs r JOIN sources s ON s.id = r.source_id
"""


def _run_row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["report"] = json.loads(d.pop("report_json") or "{}")
    return d


def list_runs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(_RUN_SELECT + " ORDER BY r.id DESC").fetchall()
    return [_run_row(r) for r in rows]


def get_run(conn: sqlite3.Connection, run_id: int) -> dict[str, Any] | None:
    row = conn.execute(_RUN_SELECT + " WHERE r.id = ?", (run_id,)).fetchone()
    return _run_row(row) if row else None


def insert_staging(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    source_id: int,
    item: dict[str, Any],
    disposition: str,
) -> None:
    conn.execute(
        """
        INSERT INTO staging_rows(
            run_id, source_id, business_key, event_ts, source_revision,
            payload_json, disposition
        ) VALUES (?,?,?,?,?,?,?)
        """,
        (
            run_id,
            source_id,
            item["business_key"],
            item["event_ts"],
            item["source_revision"],
            json.dumps(item["payload"], ensure_ascii=False),
            disposition,
        ),
    )


def list_staging(conn: sqlite3.Connection, run_id: int | None = None) -> list[dict[str, Any]]:
    if run_id is None:
        rows = conn.execute(
            """
            SELECT id, run_id, source_id, business_key, event_ts, source_revision,
                   payload_json, disposition
            FROM staging_rows ORDER BY id DESC LIMIT 200
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, run_id, source_id, business_key, event_ts, source_revision,
                   payload_json, disposition
            FROM staging_rows WHERE run_id = ? ORDER BY id
            """,
            (run_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["payload"] = json.loads(d.pop("payload_json"))
        out.append(d)
    return out


def count_staging(conn: sqlite3.Connection, run_id: int) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) c FROM staging_rows WHERE run_id = ?",
            (run_id,),
        ).fetchone()["c"]
    )


def insert_conflict(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    source_id: int,
    business_key: str,
    existing_payload: dict[str, Any],
    incoming_payload: dict[str, Any],
    reason: str,
    owner_source_id: int | None = None,
    owner_authority_rank: int | None = None,
    incoming_authority_rank: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO conflicts(
            run_id, source_id, business_key, existing_payload, incoming_payload,
            reason, owner_source_id, owner_authority_rank,
            incoming_authority_rank, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))
        """,
        (
            run_id,
            source_id,
            business_key,
            json.dumps(existing_payload, ensure_ascii=False),
            json.dumps(incoming_payload, ensure_ascii=False),
            reason,
            owner_source_id,
            owner_authority_rank,
            incoming_authority_rank,
        ),
    )


def list_conflicts(
    conn: sqlite3.Connection, run_id: int | None = None
) -> list[dict[str, Any]]:
    sql = """
        SELECT c.id, c.run_id, c.source_id, c.business_key,
               c.existing_payload, c.incoming_payload, c.reason,
               c.owner_source_id, c.owner_authority_rank,
               c.incoming_authority_rank, c.created_at,
               s.name AS source_name,
               owner.name AS owner_source_name
        FROM conflicts c
        LEFT JOIN sources s ON s.id = c.source_id
        LEFT JOIN sources owner ON owner.id = c.owner_source_id
    """
    params: tuple[Any, ...] = ()
    if run_id is not None:
        sql += " WHERE c.run_id = ?"
        params = (run_id,)
    sql += " ORDER BY c.id DESC"
    rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["existing"] = json.loads(d.pop("existing_payload"))
        d["incoming"] = json.loads(d.pop("incoming_payload"))
        out.append(d)
    return out


def count_conflicts(conn: sqlite3.Connection, run_id: int) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) c FROM conflicts WHERE run_id = ?",
            (run_id,),
        ).fetchone()["c"]
    )


def insert_authority_change(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    source_id: int,
    business_key: str,
    previous_source_id: int | None,
    previous_authority_rank: int | None,
    incoming_authority_rank: int | None,
    previous_payload: dict[str, Any],
    incoming_payload: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO authority_changes(
            run_id, source_id, business_key, previous_source_id,
            previous_authority_rank, incoming_authority_rank,
            previous_payload, incoming_payload, created_at
        ) VALUES (?,?,?,?,?,?,?,?,datetime('now'))
        """,
        (
            run_id,
            source_id,
            business_key,
            previous_source_id,
            previous_authority_rank,
            incoming_authority_rank,
            json.dumps(previous_payload, ensure_ascii=False),
            json.dumps(incoming_payload, ensure_ascii=False),
        ),
    )


def list_authority_changes(
    conn: sqlite3.Connection, run_id: int | None = None
) -> list[dict[str, Any]]:
    sql = """
        SELECT a.id, a.run_id, a.source_id, a.business_key,
               a.previous_source_id, a.previous_authority_rank,
               a.incoming_authority_rank, a.previous_payload,
               a.incoming_payload, a.created_at,
               s.name AS source_name,
               owner.name AS previous_source_name
        FROM authority_changes a
        LEFT JOIN sources s ON s.id = a.source_id
        LEFT JOIN sources owner ON owner.id = a.previous_source_id
    """
    params: tuple[Any, ...] = ()
    if run_id is not None:
        sql += " WHERE a.run_id = ?"
        params = (run_id,)
    sql += " ORDER BY a.id DESC"
    rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["previous"] = json.loads(d.pop("previous_payload"))
        d["incoming"] = json.loads(d.pop("incoming_payload"))
        out.append(d)
    return out


def count_authority_changes(conn: sqlite3.Connection, run_id: int) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) c FROM authority_changes WHERE run_id = ?",
            (run_id,),
        ).fetchone()["c"]
    )
