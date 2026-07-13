# Klareco Team Building — Dashboard

A small standalone app that structures the TB organisation: plan the monthly
event, email invites, collect ratings, and see past scores — all in one
place.

## What it does

1. **Plan / Edit Event** — pick the month, confirm the date (defaults to the
   1st Monday), write a short description, set location/cost, and choose
   participants.
2. **Send Invites** — one click opens the invite email, fully written, in
   your own email app (Outlook, Gmail, etc.) — you just hit Send there.
3. **Participants** are entered per event on the Plan/Edit screen (defaults
   to the whole team, editable).
4. **Send Rating Survey** — same idea: one click opens a ready-to-send email
   with a link to a 4-question rating form.
5. When someone submits that form, their scores are saved immediately and
   folded into that event's average — no manual step.
6. **Past Events & Scores** — a table of every event with its scores, plus a
   year-end leaderboard (same categories as the Excel version: Creativity,
   Building Team Spirit, Fun, Execution).

Data is stored in Supabase (a free hosted Postgres database) — see
**Setting up storage (Supabase)** below. This means the data survives app
restarts and redeploys, unlike the old setup where it lived in a local file.

## Making sure a month doesn't slip by unplanned

Two safeguards work together here:

- **In the app:** the Overview page shows a clear warning if the current
  month has nothing planned yet, with how many days are left to fix that.
- **Outside the app:** a Claude scheduled task ("team-building-monthly-check")
  runs on the 25th of every month, checks the database for next month's
  event, and messages Bruno directly — either a quick "all good" or a nudge
  naming whoever's up next in the rotation. This means the check happens
  even if nobody opens the app that day.

## Setting up storage (Supabase)

The app needs a Supabase database to store its data. One-time setup:

1. Go to [supabase.com](https://supabase.com), sign in with your GitHub
   account (since you've already linked it), and create a new project.
   Pick any name and a strong database password — save that password
   somewhere, you'll need it in step 3.
2. Once the project is ready, click the **"Connect"** button near the top
   of the project dashboard (not inside Project Settings — it's its own
   button). A panel opens with a few connection options; choose
   **"Transaction pooler"** (this matters — use this one, not "Direct
   connection"). Copy the connection string shown there.
3. Open (or create) a `.env` file in this folder — copy `.env.example` to
   `.env` if you haven't yet — and paste that connection string into
   `SUPABASE_DB_URL`, replacing `[YOUR-PASSWORD]` in it with the real
   database password from step 1.
4. If you already had data in the old `team_building.db` file and want to
   keep it, run this once:
   ```bash
   python migrate_sqlite_to_supabase.py
   ```
   This copies your team roster, past events, and ratings into Supabase.
   It only reads the old file, so it's safe to run.
5. When you deploy to Streamlit Community Cloud (see below), add the same
   `SUPABASE_DB_URL` value in that app's **Settings → Secrets**, so the
   deployed app talks to the same database.

That's it — Supabase now holds all the data permanently, independent of
whether or when the app itself restarts.

## Running it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

It opens at `http://localhost:8501`. The team roster is pre-filled with
Bruno, Ysaline, Jens, Basil, Tam, Jeroen — update real email addresses on
the **Team Settings** page.

## Sending emails — no setup needed by default

The **Send Invites** and **Send Rating Survey** screens write the email for
you and hand it to whatever email program you already use, with the
recipients, subject, and message pre-filled. You just check it and click
Send yourself, exactly like writing a normal email. Nothing to configure,
no password or account to give the app.

There's an "✅ I've sent it" button on each screen — click it after you've
actually sent the email, so the app can mark that event as invited/rated.

### Optional: let the app send automatically instead

If later on you'd rather the app send without you clicking Send yourself,
each send screen has an "Advanced" section for that. It needs a mailbox (or
an email-sending service) configured in a `.env` file — copy
`.env.example` to `.env` and fill in the details for Gmail, Outlook/Office
365, or a transactional service like Resend/SendGrid/Postmark. This is
optional — skip it entirely if the one-click-open-my-email-app approach
above works fine for you, which it will for most cases.

## Making it reachable by the team (not just your laptop)

Right now the app only runs on whichever machine you start it on, at an
address (`localhost`) that only means something on that one machine. For
survey links to actually open for participants, the app needs to live
somewhere always-on with a real address. This repo is already connected to
GitHub, so **Streamlit Community Cloud** (free) is the natural next step:

1. Push this folder to GitHub if you haven't already (`git add`, `git
   commit`, `git push` — the usual routine).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in, and
   click "New app". Point it at this repo and `app.py`.
3. Deploy. You'll get a permanent address like
   `https://your-app-name.streamlit.app`.
4. In that same Streamlit Cloud dashboard, open your app's **Settings →
   Secrets** and add:
   ```
   APP_BASE_URL = "https://your-app-name.streamlit.app"
   ```
   (Use the actual address from step 3.) Also add `SUPABASE_DB_URL` here —
   same value as in your `.env` file, so the deployed app talks to the same
   database. If you're also using the optional automatic-sending feature,
   add `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `FROM_EMAIL`,
   `FROM_NAME` here too — same names as in `.env`, just entered in this
   Secrets box instead of a file. The app reads either one, so nothing else
   needs to change.
5. Save — the app restarts itself with the new address, and survey links
   in emails will now be real, clickable links.

Because data lives in Supabase rather than on the app's own disk, restarts
and redeploys no longer risk losing anything — but it's still a good habit
to click the **"Download a backup (JSON)"** button on the Team Settings
page every so often, as an extra copy in your own hands.

- **Render / Railway / Fly.io** (free-to-cheap tiers) are alternatives to
  Streamlit Cloud with the same trade-off, slightly more setup but more
  control if you outgrow it.
- **A small always-on machine you already have** (e.g. a NAS, an old
  laptop, a company server) avoids the storage question entirely, since
  the disk is really yours — run `streamlit run app.py` there and set
  `APP_BASE_URL` in `.env` to its address.

## File map

- `app.py` — the whole UI, one function per screen.
- `db.py` — Postgres/Supabase schema and all data access (events, team,
  responses).
- `emailer.py` — used only by the optional automatic-sending feature; falls
  back to an on-screen preview if `.env`/Secrets aren't configured.
- `migrate_sqlite_to_supabase.py` — one-time script to bring data from the
  old `team_building.db` file into Supabase. Only needed once, when
  switching over.
- `team_building.db` — the old local database file, if you had one from
  before. No longer used by the app once `SUPABASE_DB_URL` is set; keep it
  around only as a one-time source for the migration script above.
