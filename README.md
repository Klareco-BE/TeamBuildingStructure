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

Right now the app only runs on whichever machine you start it on. For
survey links to work when participants click them, the app needs to run
somewhere always-on — not required for the invite emails themselves, which
work regardless. Cheapest/easiest options, roughly in order of effort:

- **Streamlit Community Cloud** (free) — push this folder to a private
  GitHub repo, connect it at streamlit.io/cloud, add your `.env` values as
  "secrets" in their dashboard (only needed if you're using the optional
  automatic-sending feature above). Probably the path of least resistance.
- **Render / Railway / Fly.io** (free-to-cheap tiers) — slightly more setup
  than Streamlit Cloud, but more control if you outgrow it.
- **A small always-on machine you already have** (e.g. a NAS, an old
  laptop, a company server) — run `streamlit run app.py` there and set
  `APP_BASE_URL` in `.env` to its address.

Once it's hosted somewhere with a stable URL, set `APP_BASE_URL` in `.env`
to that URL so the survey links in emails point to the right place.

## File map

- `app.py` — the whole UI, one function per screen.
- `db.py` — SQLite schema and all data access (events, team, responses).
- `emailer.py` — used only by the optional automatic-sending feature; falls
  back to an on-screen preview if `.env` isn't configured.
- `team_building.db` — created automatically on first run.
