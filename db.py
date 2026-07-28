"""
db.py — all data access for the Team Building app.

Storage: a Postgres database, meant to be a free Supabase project. This
replaces the old SQLite file so data survives app restarts and redeploys —
Supabase's storage is a real persistent database, not tied to this app's
own container.

Set SUPABASE_DB_URL (in .env locally, or as a Streamlit Cloud Secret) to
the "Connection string" from your Supabase project's Database settings —
use the "Transaction pooler" one (port 6543), which is the one meant for
apps like this that open short-lived connections. See README.md for the
full setup walkthrough.
"""
import os
import datetime
import calendar
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import psycopg2.pool
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("SUPABASE_DB_URL")

DEFAULT_TEAM = [
    ("Bruno", "bruno.fantoli@klareco.be"),
    ("Ysaline", "ysaline.thillaye@klareco.be"),
    ("Jens", "jens.heyvaert@klareco.be"),
    ("Basil", "basil.himbert@klareco.be"),
    ("Tam", "tam.nguyenvan@klareco.be"),
    ("Jeroen", "jeroen.diels@klareco.be"),
]

CATEGORIES = ["creativity", "team_spirit", "fun", "execution"]
CATEGORY_LABELS = {
    "creativity": "Creativity — was this activity original?",
    "team_spirit": "Building team spirit — do I feel closer to the team after this activity?",
    "fun": "Fun — did I have fun during the activity?",
    "execution": "Execution — did I have all the information, enough time ahead?",
}


class _CursorWrapper:
    """Makes a psycopg2 cursor behave like the sqlite3 connection.execute(...)
    calls this file used to make against the old SQLite file, so every query
    below reads the same way it always did."""

    def __init__(self, cur):
        self._cur = cur

    def execute(self, query, params=()):
        self._cur.execute(query, params)
        return self

    def executemany(self, query, seq):
        self._cur.executemany(query, seq)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()


_pool = None


def _get_pool():
    """A small set of already-open connections to Supabase, reused across
    every call instead of opening a brand new one each time. Opening a
    connection means a fresh trip over the internet to Supabase's servers
    (DNS + network handshake + login) — reusing a handful of already-open
    ones instead is what keeps the app feeling snappy rather than pausing
    on every click."""
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError(
                "SUPABASE_DB_URL isn't set. Add it to your .env file locally, or as a "
                "Streamlit Cloud Secret when deployed — see README.md for where to find "
                "this connection string in your Supabase project."
            )
        _pool = psycopg2.pool.ThreadedConnectionPool(
            1, 5, dsn=DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return _pool


@contextmanager
def get_conn():
    pool = _get_pool()
    conn = pool.getconn()

    # A connection borrowed from the pool might have gone stale while it
    # sat idle (Supabase can close quiet connections after a while). A tiny
    # "are you still there?" check is far cheaper than a fresh connection,
    # so ping it first and swap in a new one only if it's actually dead.
    try:
        with conn.cursor() as probe:
            probe.execute("SELECT 1")
    except Exception:
        conn.rollback()
        pool.putconn(conn, close=True)
        conn = pool.getconn()

    try:
        yield _CursorWrapper(conn.cursor())
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_members (
                name TEXT PRIMARY KEY,
                email TEXT
            )
        """)
        conn.execute("ALTER TABLE team_members ADD COLUMN IF NOT EXISTS sort_order INTEGER")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                month TEXT NOT NULL,
                planned_date TEXT NOT NULL,
                start_time TEXT,
                duration_hours REAL,
                organizer TEXT,
                activity TEXT,
                location TEXT,
                cost_per_person REAL,
                status TEXT DEFAULT 'Planned',
                participants TEXT DEFAULT '',
                invites_sent_at TEXT,
                survey_sent_at TEXT,
                created_at TEXT
            )
        """)
        conn.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS duration_hours REAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS organizer_queue (
                position INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                id SERIAL PRIMARY KEY,
                event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                respondent TEXT NOT NULL,
                creativity INTEGER,
                team_spirit INTEGER,
                fun INTEGER,
                execution INTEGER,
                submitted_at TEXT,
                UNIQUE(event_id, respondent)
            )
        """)
        existing = conn.execute("SELECT COUNT(*) AS c FROM team_members").fetchone()["c"]
        if existing == 0:
            conn.executemany(
                "INSERT INTO team_members (name, email, sort_order) VALUES (%s, %s, %s)",
                [(name, email, i) for i, (name, email) in enumerate(DEFAULT_TEAM)],
            )
        else:
            # Backfill sort_order for rows created before this column existed,
            # preserving the old alphabetical-by-name ordering.
            conn.execute("""
                UPDATE team_members SET sort_order = sub.rn
                FROM (
                    SELECT name, ROW_NUMBER() OVER (ORDER BY name) AS rn
                    FROM team_members WHERE sort_order IS NULL
                ) AS sub
                WHERE team_members.name = sub.name
            """)


# ---------------------------------------------------------------- team members
def list_team_members():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name, email FROM team_members ORDER BY sort_order, name"
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_team_member(name, email):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO team_members (name, email, sort_order) "
            "VALUES (%s, %s, COALESCE((SELECT MAX(sort_order) + 1 FROM team_members), 0)) "
            "ON CONFLICT(name) DO UPDATE SET email=excluded.email",
            (name.strip(), email.strip()),
        )


def delete_team_member(name):
    with get_conn() as conn:
        conn.execute("DELETE FROM team_members WHERE name = %s", (name,))


def move_team_member(name, offset):
    """Swap `name` with the member `offset` slots away (-1 for up, +1 for down)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name, sort_order FROM team_members ORDER BY sort_order, name"
        ).fetchall()
        names = [r["name"] for r in rows]
        if name not in names:
            return
        idx = names.index(name)
        swap_idx = idx + offset
        if swap_idx < 0 or swap_idx >= len(names):
            return
        conn.execute(
            "UPDATE team_members SET sort_order = %s WHERE name = %s",
            (rows[swap_idx]["sort_order"], rows[idx]["name"]),
        )
        conn.execute(
            "UPDATE team_members SET sort_order = %s WHERE name = %s",
            (rows[idx]["sort_order"], rows[swap_idx]["name"]),
        )


# ---------------------------------------------------------------- rotation helpers
def first_monday(year, month):
    """Return the date of the first Monday of the given year/month."""
    d = datetime.date(year, month, 1)
    offset = (7 - d.weekday()) % 7 if d.weekday() != 0 else 0
    return d + datetime.timedelta(days=offset)


def month_options(n=12):
    """Next n months as (label, 'YYYY-MM') starting this month."""
    today = datetime.date.today()
    opts = []
    y, m = today.year, today.month
    for i in range(n):
        mm = (m - 1 + i) % 12 + 1
        yy = y + (m - 1 + i) // 12
        opts.append((f"{calendar.month_name[mm]} {yy}", f"{yy}-{mm:02d}"))
    return opts


def get_rotation_queue():
    """The ordered list of upcoming organizers. Position 0 is up next, then 1,
    etc. Kept in sync with the team roster: new members are appended at the
    back, removed members drop out of the queue."""
    team = [t["name"] for t in list_team_members()]
    with get_conn() as conn:
        rows = conn.execute("SELECT name FROM organizer_queue ORDER BY position").fetchall()
        queue = [r["name"] for r in rows]

        synced = [n for n in queue if n in team] + [n for n in team if n not in queue]
        if synced != queue:
            conn.execute("DELETE FROM organizer_queue")
            conn.executemany(
                "INSERT INTO organizer_queue (position, name) VALUES (%s, %s)",
                list(enumerate(synced)),
            )
        return synced


def set_rotation_queue(names):
    with get_conn() as conn:
        conn.execute("DELETE FROM organizer_queue")
        conn.executemany(
            "INSERT INTO organizer_queue (position, name) VALUES (%s, %s)",
            list(enumerate(names)),
        )


def get_next_organizer():
    """Suggest the next organizer — the front of the rotation queue."""
    queue = get_rotation_queue()
    return queue[0] if queue else ""


# ---------------------------------------------------------------- events
def create_event(month, planned_date, start_time, organizer, activity, location,
                  cost_per_person, participants, duration_hours=None):
    with get_conn() as conn:
        row = conn.execute(
            """INSERT INTO events
               (month, planned_date, start_time, duration_hours, organizer, activity, location,
                cost_per_person, status, participants, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Planned', %s, %s)
               RETURNING id""",
            (month, planned_date, start_time, duration_hours, organizer, activity, location,
             cost_per_person, ",".join(participants),
             datetime.datetime.now().isoformat(timespec="seconds")),
        ).fetchone()
        return row["id"]


def update_event(event_id, **fields):
    if not fields:
        return
    if "participants" in fields and isinstance(fields["participants"], list):
        fields["participants"] = ",".join(fields["participants"])
    cols = ", ".join(f"{k} = %s" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE events SET {cols} WHERE id = %s", (*fields.values(), event_id))


def get_event(event_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM events WHERE id = %s", (event_id,)).fetchone()
        return dict(row) if row else None


def list_events(order="desc"):
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM events ORDER BY planned_date {'DESC' if order == 'desc' else 'ASC'}"
        ).fetchall()
        return [dict(r) for r in rows]


def delete_event(event_id):
    """Delete an event and any ratings submitted for it (responses.event_id
    cascades on delete, declared in the table itself — no extra step needed)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM events WHERE id = %s", (event_id,))


def month_has_event(month_value):
    """True if an event already exists for the given 'YYYY-MM' month —
    used to flag a month that's at risk of slipping by unplanned."""
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM events WHERE month = %s LIMIT 1", (month_value,)).fetchone()
        return row is not None


def mark_invites_sent(event_id):
    update_event(event_id, invites_sent_at=datetime.datetime.now().isoformat(timespec="seconds"),
                  status="Confirmed")


def mark_survey_sent(event_id):
    update_event(event_id, survey_sent_at=datetime.datetime.now().isoformat(timespec="seconds"),
                  status="Done")


# ---------------------------------------------------------------- responses
def record_response(event_id, respondent, scores: dict):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO responses (event_id, respondent, creativity, team_spirit, fun,
                                       execution, submitted_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT(event_id, respondent) DO UPDATE SET
                 creativity=excluded.creativity, team_spirit=excluded.team_spirit,
                 fun=excluded.fun, execution=excluded.execution,
                 submitted_at=excluded.submitted_at""",
            (event_id, respondent, scores["creativity"], scores["team_spirit"],
             scores["fun"], scores["execution"],
             datetime.datetime.now().isoformat(timespec="seconds")),
        )


def get_responses(event_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM responses WHERE event_id = %s ORDER BY submitted_at", (event_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_event_scores(event_id):
    """Per-category averages + overall total for one event, or None if no
    responses yet."""
    rows = get_responses(event_id)
    if not rows:
        return None
    avgs = {}
    for cat in CATEGORIES:
        vals = [r[cat] for r in rows if r[cat] is not None]
        avgs[cat] = round(sum(vals) / len(vals), 2) if vals else None
    valid = [v for v in avgs.values() if v is not None]
    avgs["total"] = round(sum(valid) / len(valid), 2) if valid else None
    avgs["n_responses"] = len(rows)
    return avgs


def get_leaderboard(year=None):
    """Average total score per organizer, optionally filtered to a year."""
    events = list_events()
    if year:
        events = [e for e in events if e["planned_date"][:4] == str(year)]
    totals = {}
    for e in events:
        scores = get_event_scores(e["id"])
        if scores and scores["total"] is not None:
            totals.setdefault(e["organizer"], []).append(scores["total"])
    board = []
    for organizer, vals in totals.items():
        board.append({
            "organizer": organizer,
            "events": len(vals),
            "avg_score": round(sum(vals) / len(vals), 2),
        })
    board.sort(key=lambda x: x["avg_score"], reverse=True)
    for i, row in enumerate(board, start=1):
        row["rank"] = i
    return board


# ---------------------------------------------------------------- backup / export
def export_all_data():
    """Everything in the database, as plain dicts/lists — used for the
    on-demand JSON backup download (Supabase itself also keeps its own
    backups, this is just an extra copy in your own hands)."""
    with get_conn() as conn:
        team = conn.execute("SELECT name, email FROM team_members ORDER BY name").fetchall()
        events = conn.execute("SELECT * FROM events ORDER BY id").fetchall()
        responses = conn.execute("SELECT * FROM responses ORDER BY id").fetchall()
        queue = conn.execute("SELECT position, name FROM organizer_queue ORDER BY position").fetchall()
    return {
        "team_members": [dict(r) for r in team],
        "events": [dict(r) for r in events],
        "responses": [dict(r) for r in responses],
        "organizer_queue": [dict(r) for r in queue],
    }
