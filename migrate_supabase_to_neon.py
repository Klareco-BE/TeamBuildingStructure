# migrate_supabase_to_neon.py
import os
import psycopg2
import psycopg2.extras

OLD_URL = "postgresql://postgres.aiefcgdvsqtgrbuxfszk:8yq4gk10iVMfglOi@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
NEW_URL = "postgresql://neondb_owner:npg_U29cfVzOKoie@ep-gentle-lab-b1lkegrx-pooler.c-5.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

TABLES = ["team_members", "organizer_queue", "events", "responses"]


def main():
    src = psycopg2.connect(OLD_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    dst = psycopg2.connect(NEW_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    src_cur, dst_cur = src.cursor(), dst.cursor()

    print("Ensuring schema exists on Neon...")
    dst_cur.execute("""CREATE TABLE IF NOT EXISTS team_members (name TEXT PRIMARY KEY, email TEXT)""")
    dst_cur.execute("ALTER TABLE team_members ADD COLUMN IF NOT EXISTS sort_order INTEGER")
    dst_cur.execute("""CREATE TABLE IF NOT EXISTS events (
        id SERIAL PRIMARY KEY, month TEXT NOT NULL, planned_date TEXT NOT NULL,
        start_time TEXT, duration_hours REAL, organizer TEXT, activity TEXT,
        location TEXT, cost_per_person REAL, status TEXT DEFAULT 'Planned',
        participants TEXT DEFAULT '', invites_sent_at TEXT, survey_sent_at TEXT,
        created_at TEXT)""")
    dst_cur.execute("""CREATE TABLE IF NOT EXISTS organizer_queue (
        position INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)""")
    dst_cur.execute("""CREATE TABLE IF NOT EXISTS responses (
        id SERIAL PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        respondent TEXT NOT NULL, creativity INTEGER, team_spirit INTEGER, fun INTEGER,
        execution INTEGER, submitted_at TEXT, UNIQUE(event_id, respondent))""")
    dst.commit()

    print("Clearing any seed/test data currently on Neon...")
    dst_cur.execute("TRUNCATE TABLE responses, events, organizer_queue, team_members RESTART IDENTITY CASCADE")
    dst.commit()

    counts = {}
    for table in TABLES:
        src_cur.execute(f"SELECT * FROM {table}")
        rows = src_cur.fetchall()
        counts[table] = len(rows)
        if not rows:
            print(f"{table}: 0 rows on Supabase, nothing to copy")
            continue
        cols = list(rows[0].keys())
        dst_cur.executemany(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s']*len(cols))})",
            [tuple(r[c] for c in cols) for r in rows],
        )
        dst.commit()
        print(f"{table}: copied {len(rows)} row(s)")

    for table in ("events", "responses"):
        dst_cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1))")
    dst.commit()

    print("\nVerifying...")
    ok = True
    for table in TABLES:
        dst_cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
        n = dst_cur.fetchone()["c"]
        status = "OK" if n == counts[table] else "MISMATCH"
        ok &= (n == counts[table])
        print(f"  {table}: supabase={counts[table]} neon={n} [{status}]")

    src.close(); dst.close()
    print("\nAll counts match." if ok else "\nSomething doesn't match, check above.")


if __name__ == "__main__":
    main()