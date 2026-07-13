# Klareco Team Building — Dashboard

A small standalone app that replaces the Excel structure: plan the monthly
event, email invites, collect ratings, and see past scores — all in one
place.

## What it does

1. **Plan / Edit Event** — pick the month, confirm the date (defaults to the
   1st Monday), write a short description, set location/cost, and choose
   participants.
2. **Send Invites** — one click emails everyone selected as a participant,
   with the date, description, and practical info.
3. **Participants** are entered per event on the Plan/Edit screen (defaults
   to the whole team, editable).
4. **Send Rating Survey** — one click emails each participant a personal
   link to a 4-question rating form.
5. When someone submits that form, their scores are saved immediately and
   folded into that event's average — no manual step.
6. **Past Events & Scores** — a table of every event with its scores, plus a
   year-end leaderboard (same categories as the Excel version: Creativity,
   Building Team Spirit, Fun, Execution).

Data is stored in `team_building.db`, a single SQLite file created
automatically next to the app — nothing else to install or manage.

## Running it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

It opens at `http://localhost:8501`. The team roster is pre-filled with
Bruno, Ysaline, Jens, Basil, Tam, Jeroen — update real email addresses on
the **Team Settings** page.

## Turning on real email

Copy `.env.example` to `.env` and fill in SMTP details for whatever mailbox
you want invites/surveys to come from (Gmail, Outlook/Office 365, or a
transactional service like Resend/SendGrid/Postmark — any of them work,
they all speak SMTP). Until you do this, the "send" buttons show you the
exact email that *would* be sent, so you can test the rest of the app
immediately.

## Making it reachable by the team (not just your laptop)

Right now the app only runs on whichever machine you start it on. For
invites and survey links to work for everyone, it needs to run somewhere
always-on. Cheapest/easiest options, roughly in order of effort:

- **Streamlit Community Cloud** (free) — push this folder to a private
  GitHub repo, connect it at streamlit.io/cloud, add your `.env` values as
  "secrets" in their dashboard. Probably the path of least resistance.
- **Render / Railway / Fly.io** (free-to-cheap tiers) — slightly more setup
  than Streamlit Cloud, but more control if you outgrow it.
- **A small always-on machine you already have** (e.g. a NAS, an old
  laptop, a company server) — run `streamlit run app.py` there and set
  `APP_BASE_URL` in `.env` to its address.

Once it's hosted somewhere with a stable URL, set `APP_BASE_URL` in `.env`
to that URL so the survey links in emails point to the right place.

## Why Streamlit (and what else was considered)

You mentioned Streamlit — it's a solid fit here and is what this first
version uses:

- **Streamlit (this build).** Plain Python, one file per screen, no
  frontend code to maintain. Best if you (or anyone at Klareco who knows a
  little Python) want to keep tweaking it yourselves. Downside: needs
  hosting somewhere for the team to reach it (see above), and email
  requires your own SMTP credentials.
- **Google Forms + Sheets + Apps Script.** Zero hosting — everything lives
  in Google's infrastructure. Apps Script can send the invite/survey emails
  directly from your Gmail and write responses straight into a Sheet. Very
  low maintenance, but the "dashboard" feel is weaker (it's really a sheet
  plus a couple of scripts), and customizing the UI takes more
  Apps-Script-specific know-how than editing Python.
- **Airtable (or Notion) + built-in automations.** Nicer-looking interface
  out of the box, built-in forms, and automations can send emails without
  writing code. Costs more once you're on features like automations at
  scale, and you're more limited by what the platform allows.
- **Retool / Glide.** No-code internal-tool builders, good for more complex
  dashboards with many data sources. Overkill for six people and one
  monthly event, and both are paid products.

For a 6-person team with this specific set of features, Streamlit keeps you
in full control and costs nothing to run, at the cost of needing a few
minutes of hosting/email setup up front. Happy to switch approaches if you'd
rather trade that setup for a no-code option.

## File map

- `app.py` — the whole UI, one function per screen.
- `db.py` — SQLite schema and all data access (events, team, responses).
- `emailer.py` — sends email via SMTP; falls back to an on-screen preview.
- `team_building.db` — created automatically on first run.
