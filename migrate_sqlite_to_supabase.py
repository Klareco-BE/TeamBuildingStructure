"""
One-time helper: copies everything from the old team_building.db (SQLite)
into your new Supabase database, so past events and ratings aren't lost
when switching over.

Run once, locally:

    python migrate_sqlite_to_supabase.py

Before running: make sure SUPABASE_DB_URL is set in your .env file (see
.env.example and README.md). Your old team_building.db file is only read
from, never modified — safe to run, and safe to re-run if something goes
wrong.
"""
import sqlite3
from pathlib import Path

import db  # the Supabase-backed db.py

OLD_DB_PATH = Path(__file__).parent / "team_building.db"


def main():
    if not OLD_DB_PATH.exists():
        print(f"No old database found at {OLD_DB_PATH} — nothing to migrate.")
        return

    print("Setting up tables in Supabase (safe to run even if they already exist)...")
    db.init_db()

    old = sqlite3.connect(OLD_DB_PATH)
    old.row_factory = sqlite3.Row

    team = old.execute("SELECT name, email FROM team_members").fetchall()
    for t in team:
        db.upsert_team_member(t["name"], t["email"] or "")
    print(f"Migrated {len(team)} team member(s).")

    events = old.execute("SELECT * FROM events ORDER BY id").fetchall()
    id_map = {}
    for e in events:
        participants = [p for p in (e["participants"] or "").split(",") if p]
        duration = e["duration_hours"] if "duration_hours" in e.keys() else None
        new_id = db.create_event(
            e["month"], e["planned_date"], e["start_time"], e["organizer"],
            e["activity"], e["location"], e["cost_per_person"], participants,
            duration_hours=duration,
        )
        id_map[e["id"]] = new_id
        db.update_event(
            new_id, status=e["status"], invites_sent_at=e["invites_sent_at"],
            survey_sent_at=e["survey_sent_at"],
        )
    print(f"Migrated {len(events)} event(s).")

    responses = old.execute("SELECT * FROM responses").fetchall()
    migrated_responses = 0
    for r in responses:
        if r["event_id"] in id_map:
            db.record_response(id_map[r["event_id"]], r["respondent"], {
                "creativity": r["creativity"],
                "team_spirit": r["team_spirit"],
                "fun": r["fun"],
                "execution": r["execution"],
            })
            migrated_responses += 1
    print(f"Migrated {migrated_responses} response(s).")

    old.close()
    print("Done. Your old team_building.db is untouched — the app now reads and "
          "writes to Supabase instead, so this file is just an old backup from now on.")


if __name__ == "__main__":
    main()
