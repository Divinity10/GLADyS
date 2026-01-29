"""Database query module — read access to GLADyS PostgreSQL schema.

Provides reusable query functions for episodic_events, heuristics,
and heuristic_fires. Used by the dashboard backend and potentially
the admin CLI.

Connection uses psycopg2 (synchronous) with DSN built from the
same env vars / port config as the rest of the admin scripts.
"""

import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

from _gladys import LOCAL_PORTS, DOCKER_PORTS


def get_dsn(mode: str = "local") -> str:
    """Build a psycopg2 DSN string for the given environment."""
    ports = DOCKER_PORTS if mode == "docker" else LOCAL_PORTS
    host = os.environ.get("DB_HOST", "localhost")
    name = os.environ.get("DB_NAME", "gladys")
    user = os.environ.get("DB_USER", "gladys")
    pw = os.environ.get("DB_PASS", "gladys")
    return f"host={host} port={ports.db} dbname={name} user={user} password={pw}"


def _connect(dsn: str):
    """Open a connection with RealDictCursor default."""
    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


# ---------------------------------------------------------------------------
# episodic_events
# ---------------------------------------------------------------------------

def list_events(dsn: str, *, limit: int = 50, offset: int = 0,
                source: str = None) -> list[dict]:
    """List recent episodic events, newest first.

    Returns dicts with keys: id, timestamp, source, raw_text, salience,
    response_text, response_id, predicted_success, prediction_confidence.
    """
    conn = _connect(dsn)
    try:
        cur = conn.cursor()
        query = """
            SELECT id, timestamp, source, raw_text,
                   salience, response_text, response_id,
                   predicted_success, prediction_confidence
            FROM episodic_events
            WHERE archived = false
        """
        params = []

        if source:
            query += " AND source = %s"
            params.append(source)

        query += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, params)
        rows = cur.fetchall()
        # RealDictCursor returns RealDictRow; convert to plain dicts
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_event(dsn: str, event_id: str) -> dict | None:
    """Fetch a single event by ID. Returns None if not found."""
    conn = _connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, timestamp, source, raw_text,
                   salience, response_text, response_id,
                   predicted_success, prediction_confidence
            FROM episodic_events
            WHERE id = %s
        """, [event_id])
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def count_events(dsn: str, *, source: str = None) -> int:
    """Count non-archived events, optionally filtered by source."""
    conn = _connect(dsn)
    try:
        cur = conn.cursor()
        query = "SELECT COUNT(*) AS cnt FROM episodic_events WHERE archived = false"
        params = []
        if source:
            query += " AND source = %s"
            params.append(source)
        cur.execute(query, params)
        return cur.fetchone()["cnt"]
    finally:
        conn.close()


def delete_event(dsn: str, event_id: str) -> bool:
    """Archive a single event by ID. Returns True if found."""
    conn = _connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE episodic_events SET archived = true WHERE id = %s AND archived = false",
            [event_id],
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_all_events(dsn: str) -> int:
    """Archive all non-archived events. Returns count archived."""
    conn = _connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE episodic_events SET archived = true WHERE archived = false")
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# heuristics
# ---------------------------------------------------------------------------

def list_heuristics(dsn: str, *, limit: int = 50, offset: int = 0,
                    include_frozen: bool = False) -> list[dict]:
    """List heuristics, highest confidence first.

    Returns dicts with keys: id, name, condition, action, confidence,
    fire_count, success_count, frozen, origin, created_at, updated_at.
    """
    conn = _connect(dsn)
    try:
        cur = conn.cursor()
        query = """
            SELECT id, name, condition, action, confidence,
                   fire_count, success_count, frozen, origin,
                   created_at, updated_at
            FROM heuristics
        """
        params = []

        if not include_frozen:
            query += " WHERE frozen = false"

        query += " ORDER BY confidence DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def count_heuristics(dsn: str, *, include_frozen: bool = False) -> int:
    """Count heuristics."""
    conn = _connect(dsn)
    try:
        cur = conn.cursor()
        query = "SELECT COUNT(*) AS cnt FROM heuristics"
        if not include_frozen:
            query += " WHERE frozen = false"
        cur.execute(query)
        return cur.fetchone()["cnt"]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# heuristic_fires
# ---------------------------------------------------------------------------

def list_fires(dsn: str, *, limit: int = 25, offset: int = 0,
               outcome: str = None) -> list[dict]:
    """List recent heuristic fires with heuristic metadata.

    Returns dicts with keys: id, heuristic_id, event_id, fired_at,
    outcome, feedback_source, feedback_at, episodic_event_id,
    heuristic_name, condition_text, confidence.
    """
    conn = _connect(dsn)
    try:
        cur = conn.cursor()
        query = """
            SELECT hf.id, hf.heuristic_id, hf.event_id, hf.fired_at,
                   hf.outcome, hf.feedback_source, hf.feedback_at,
                   hf.episodic_event_id,
                   h.name AS heuristic_name,
                   h.condition->>'text' AS condition_text,
                   h.confidence
            FROM heuristic_fires hf
            LEFT JOIN heuristics h ON h.id = hf.heuristic_id
            WHERE 1=1
        """
        params = []

        if outcome:
            query += " AND hf.outcome = %s"
            params.append(outcome)

        query += " ORDER BY hf.fired_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def count_fires(dsn: str, *, outcome: str = None) -> int:
    """Count heuristic fires."""
    conn = _connect(dsn)
    try:
        cur = conn.cursor()
        query = "SELECT COUNT(*) AS cnt FROM heuristic_fires"
        params = []
        if outcome:
            query += " WHERE outcome = %s"
            params.append(outcome)
        cur.execute(query, params)
        return cur.fetchone()["cnt"]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------

def get_metrics(dsn: str) -> dict:
    """Get aggregate metrics across tables.

    Returns dict with keys: total_events, queued_events,
    active_heuristics, total_fires.
    """
    conn = _connect(dsn)
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM episodic_events WHERE archived = false
        """)
        total_events = cur.fetchone()["total"]

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM episodic_events
            WHERE archived = false AND response_id IS NOT NULL
        """)
        queued_events = cur.fetchone()["total"]

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM heuristics WHERE frozen = false
        """)
        active_heuristics = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM heuristic_fires")
        total_fires = cur.fetchone()["total"]

        return {
            "total_events": total_events,
            "queued_events": queued_events,
            "active_heuristics": active_heuristics,
            "total_fires": total_fires,
        }
    finally:
        conn.close()
