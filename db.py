"""
db.py — all data access for the Team Building app.

Storage: a single SQLite file (team_building.db) sitting next to this script.
No external database needed — this keeps the whole app copy-pasteable and
easy to back up (it's just one extra file).
"""
import sqlite3
import datetime
import calendar
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "team_building.db"

DEFAULT_TEAM = [
    ("Bruno", "bruno.fantoli@klareco.be"),
    ("Ysaline", "ysaline@klareco.be"),
    ("Jens", "jens@klareco.be"),
    ("Basil", "basil@klareco.be"),
    ("Tam", "tam@klareco.be"),
    ("Jeroen", "jeroen@klareco.be"),
]

CATEGORIES = ["creativity", "team_spirit", "fun", "execution"]
CATEGORY_LABELS = {
    "creativity": "Creativity — was this activity original?",
    "team_spirit": "Building team spirit — do I feel closer to the team after this activity?",
    "fun": "Fun — did I have fun during the activity?",
    "execution": "Execution — did I have all the information, enough time ahead?",
}


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_members (
                name TEXT PRIMARY KEY,
                email TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
        if "duration_hours" not in existing_cols:
            conn.execute("ALTER TABLE events ADD COLUMN duration_hours REAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS organizer_queue (
                position INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                "INSERT INTO team_members (name, email) VALUES (?, ?)", DEFAULT_TEAM
            )


# ---------------------------------------------------------------- team members
def list_team_members():
    with get_conn() as conn:
        rows = conn.execute("SELECT name, email FROM team_members ORDER BY rowid").fetchall()
        return [dict(r) for r in rows]


def upsert_team_member(name, email):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO team_members (name, email) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET email=excluded.email",
            (name.strip(), email.strip()),
        )


def delete_team_member(name):
    with get_conn() as conn:
        conn.execute("DELETE FROM team_members WHERE name = ?", (name,))


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
        rows = conn.execute(
            "SELECT name FROM organizer_queue ORDER BY position"
        ).fetchall()
        queue = [r["name"] for r in rows]

        synced = [n for n in queue if n in team] + [n for n in team if n not in queue]
        if synced != queue:
            conn.execute("DELETE FROM organizer_queue")
            conn.executemany(
                "INSERT INTO organizer_queue (position, name) VALUES (?, ?)",
                list(enumerate(synced)),
            )
        return synced


def set_rotation_queue(names):
    with get_conn() as conn:
        conn.execute("DELETE FROM organizer_queue")
        conn.executemany(
            "INSERT INTO organizer_queue (position, name) VALUES (?, ?)",
            list(enumerate(names)),
        )


def move_organizer_to_slot(name, slot_index):
    """Move `name` to `slot_index` in the rotation queue, shifting everyone
    between their old and new spot over by one — e.g. moving someone from
    slot 2 up to slot 0 pushes the previous slot-0 and slot-1 people back by
    one each."""
    queue = get_rotation_queue()
    if name not in queue:
        return
    queue.remove(name)
    slot_index = max(0, min(slot_index, len(queue)))
    queue.insert(slot_index, name)
    set_rotation_queue(queue)


def get_next_organizer():
    """Suggest the next organizer — the front of the rotation queue."""
    queue = get_rotation_queue()
    return queue[0] if queue else ""


# ---------------------------------------------------------------- events
def create_event(month, planned_date, start_time, organizer, activity, location,
                  cost_per_person, participants, duration_hours=None):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO events
               (month, planned_date, start_time, duration_hours, organizer, activity, location,
                cost_per_person, status, participants, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Planned', ?, ?)""",
            (month, planned_date, start_time, duration_hours, organizer, activity, location,
             cost_per_person, ",".join(participants),
             datetime.datetime.now().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def update_event(event_id, **fields):
    if not fields:
        return
    if "participants" in fields and isinstance(fields["participants"], list):
        fields["participants"] = ",".join(fields["participants"])
    cols = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE events SET {cols} WHERE id = ?", (*fields.values(), event_id))


def get_event(event_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return dict(row) if row else None


def list_events(order="desc"):
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM events ORDER BY planned_date {'DESC' if order == 'desc' else 'ASC'}"
        ).fetchall()
        return [dict(r) for r in rows]


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
               VALUES (?, ?, ?, ?, ?, ?, ?)
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
            "SELECT * FROM responses WHERE event_id = ? ORDER BY submitted_at", (event_id,)
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
