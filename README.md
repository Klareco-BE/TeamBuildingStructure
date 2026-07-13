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

## Making sure a month doesn't slip by unplanned

Two safeguards work together here:

- **In the app:** the Overview page shows a clear warning if the current
  month has nothing planned yet, with how many days are left to fix that.
- **Outside the app:** a Claude scheduled task ("team-building-monthly-check")
  runs on the 25th of every month, checks the database for next month's
  event, and messages Bruno directly — either a quick "all good" or a nudge
  naming whoever's up next in the rotation. This means the check happens
  even if nobody opens the app that day.

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
   (Use the actual address from step 3.) If you're also using the optional
   automatic-sending feature, add `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
   `SMTP_PASSWORD`, `FROM_EMAIL`, `FROM_NAME` here too — same names as in
   `.env`, just entered in this Secrets box instead of a file. The app
   reads either one, so nothing else needs to change.
5. Save — the app restarts itself with the new address, and survey links
   in emails will now be real, clickable links.

One thing worth knowing: a free Streamlit Cloud app's storage isn't
guaranteed to stick around forever — if the app restarts (which can happen
on its own after a while, or whenever you push a code update), it starts
fresh from what's in the GitHub repo, not necessarily what was typed in
during the last session. For a 6-person tool this is a minor inconvenience
rather than a disaster, but to be safe: there's a **"Download a backup of
the database"** button on the Team Settings page — get in the habit of
clicking it every so often (e.g. after each month's ratings come in) so
you always have your event history saved on your own computer too.

- **Render / Railway / Fly.io** (free-to-cheap tiers) are alternatives to
  Streamlit Cloud with the same trade-off, slightly more setup but more
  control if you outgrow it.
- **A small always-on machine you already have** (e.g. a NAS, an old
  laptop, a company server) avoids the storage question entirely, since
  the disk is really yours — run `streamlit run app.py` there and set
  `APP_BASE_URL` in `.env` to its address.

## File map

- `app.py` — the whole UI, one function per screen.
- `db.py` — SQLite schema and all data access (events, team, responses).
- `emailer.py` — used only by the optional automatic-sending feature; falls
  back to an on-screen preview if `.env`/Secrets aren't configured.
- `team_building.db` — created automatically on first run. Back it up from
  the Team Settings page once the app is deployed somewhere.
