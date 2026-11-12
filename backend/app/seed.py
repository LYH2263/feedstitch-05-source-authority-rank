from app.db import connect

DEFAULT_AUTHORITY_RANKS = {
    "Alpha Catalog": 100,
    "Beta Offers": 10,
    "Gamma Shelf": 50,
}


def _table_columns(conn, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _ensure_column(conn, table: str, column: str, definition: str) -> bool:
    """Add a column to an existing SQLite database.

    Returns True only when the column was actually created, which lets the
    seed step apply sensible authority ranks to databases created before this
    feature existed without overwriting ranks the user later edits.
    """

    if column in _table_columns(conn, table):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    return True


def _apply_default_authority_ranks(conn) -> None:
    for name, rank in DEFAULT_AUTHORITY_RANKS.items():
        conn.execute(
            "UPDATE sources SET authority_rank = ? WHERE name = ? AND authority_rank = 0",
            (rank, name),
        )


def init_db():
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS sources(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            format TEXT NOT NULL,
            fixture_path TEXT NOT NULL,
            watermark_ts TEXT,
            lookback_seconds INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            authority_rank INTEGER NOT NULL DEFAULT 0,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS runs(
            id INTEGER PRIMARY KEY,
            source_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            parsed_count INTEGER NOT NULL,
            upserted_count INTEGER NOT NULL,
            conflict_count INTEGER NOT NULL,
            authority_isolated_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL,
            report_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS staging_rows(
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL,
            source_id INTEGER NOT NULL,
            business_key TEXT NOT NULL,
            event_ts TEXT NOT NULL,
            source_revision INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            disposition TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS canonical_items(
            id INTEGER PRIMARY KEY,
            business_key TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            price REAL NOT NULL,
            category TEXT NOT NULL,
            source_id INTEGER NOT NULL,
            event_ts TEXT NOT NULL,
            source_revision INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS conflicts(
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL,
            source_id INTEGER NOT NULL,
            business_key TEXT NOT NULL,
            existing_payload TEXT NOT NULL,
            incoming_payload TEXT NOT NULL,
            reason TEXT NOT NULL,
            owner_source_id INTEGER,
            owner_authority_rank INTEGER,
            incoming_authority_rank INTEGER,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS authority_changes(
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL,
            source_id INTEGER NOT NULL,
            business_key TEXT NOT NULL,
            previous_source_id INTEGER,
            previous_authority_rank INTEGER,
            incoming_authority_rank INTEGER,
            previous_payload TEXT NOT NULL,
            incoming_payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )

    # Upgrade databases created before source authority ranks existed.
    rank_column_added = _ensure_column(
        conn, "sources", "authority_rank", "INTEGER NOT NULL DEFAULT 0"
    )
    _ensure_column(
        conn, "runs", "authority_isolated_count", "INTEGER NOT NULL DEFAULT 0"
    )
    _ensure_column(conn, "conflicts", "owner_source_id", "INTEGER")
    _ensure_column(conn, "conflicts", "owner_authority_rank", "INTEGER")
    _ensure_column(conn, "conflicts", "incoming_authority_rank", "INTEGER")

    if conn.execute("SELECT COUNT(*) c FROM sources").fetchone()["c"] == 0:
        conn.executemany(
            """
            INSERT INTO sources(
                name, format, fixture_path, watermark_ts, lookback_seconds,
                enabled, authority_rank, note
            )
            VALUES (?,?,?,?,?,?,?,?)
            """,
            [
                (
                    "Alpha Catalog",
                    "json",
                    "alpha_catalog.json",
                    None,
                    0,
                    1,
                    100,
                    "clean：三件独立货号；权威序 100（最高）",
                ),
                (
                    "Beta Offers",
                    "jsonl",
                    "beta_offers.jsonl",
                    None,
                    0,
                    1,
                    10,
                    "dirty：SKU-1001 与 Alpha 同键异价；权威序 10（低）",
                ),
                (
                    "Gamma Shelf",
                    "xml",
                    "gamma_shelf.xml",
                    None,
                    0,
                    1,
                    50,
                    "xml 源：两件独立货号；权威序 50",
                ),
            ],
        )
        conn.execute("INSERT INTO settings(key, value) VALUES ('project_label', 'Feedstitch')")
        conn.execute("INSERT INTO settings(key, value) VALUES ('default_mode', 'incremental')")
    elif rank_column_added:
        _apply_default_authority_ranks(conn)

    conn.commit()
    conn.close()
