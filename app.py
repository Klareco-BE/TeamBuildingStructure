"""
Klareco Team Building — standalone dashboard.

Run locally:      streamlit run app.py
Data lives in:     Supabase (Postgres) — set SUPABASE_DB_URL in .env,
                    see README.md's "Setting up storage" section.
Email:             by default, "send" buttons open the message in your own
                    email app (Outlook, Gmail, etc.) so you just hit Send
                    yourself — nothing to configure. If you'd rather have
                    the app send automatically without you clicking Send in
                    your own mailbox, there's an optional "Advanced" section
                    on each send screen for that (needs SMTP setup, see
                    README.md).
"""
import datetime
import json
import os
import urllib.parse

import streamlit as st
from streamlit_sortables import sort_items

import db
import emailer

st.set_page_config(page_title="Klareco Team Building", page_icon="🎉", layout="wide")
db.init_db()

# If this app is deployed on Streamlit Community Cloud, values set in its
# "Secrets" panel show up in st.secrets, not as environment variables. Copy
# them across so the rest of the app (and emailer.py) can keep reading
# plain environment variables either way, whether running locally with a
# .env file or deployed with Secrets.
try:
    for _k, _v in st.secrets.items():
        os.environ.setdefault(_k, str(_v))
except Exception:
    pass

GROUND_RULES = """
- **Frequency:** once a month.
- **When:** Monday evening, 1–3 hours. Default is the 1st Monday of the month — move it if that
  doesn't work.
- **Budget:** max €30 per person.
- **Organizer:** rotates every month through the team list.
- **Flexibility:** if no Monday works that month, agree an alternative date with the team rather
  than skipping it.
"""


# ============================================================================
# Helpers
# ============================================================================
def base_url():
    return os.getenv("APP_BASE_URL", "http://localhost:8501")


def links_are_local():
    """True if survey links still point at localhost — meaning they'll only
    work on this machine, not for other participants."""
    return "localhost" in base_url() or "127.0.0.1" in base_url()


def respond_link(event_id, person=None):
    """A link to the rating form. If person is given, the form pre-fills who's
    answering; if not, whoever opens it just types their own name."""
    params = {"respond": "1", "event": event_id}
    if person:
        params["person"] = person
    return f"{base_url()}/?{urllib.parse.urlencode(params)}"


def mailto_url(to_emails, subject, body):
    """Build a mailto: link that opens the user's own email app with the
    recipients, subject, and message already filled in — no email account
    or password needs to be given to this app at all."""
    to_part = ",".join(e for e in to_emails if e)
    query = f"subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"
    return f"mailto:{to_part}?{query}"


def status_badge(status):
    colors = {"Planned": "🔵", "Confirmed": "🟢", "Done": "⚪"}
    return f"{colors.get(status, '⚪')} {status}"


def team_email_map():
    return {t["name"]: t["email"] for t in db.list_team_members()}


def format_duration(hours):
    if not hours:
        return None
    if hours == int(hours):
        h = int(hours)
        return f"{h} hour" if h == 1 else f"{h} hours"
    return f"{hours:g} hours"


def event_numbers():
    """Map each event's real database id to a compact, gap-free display
    number (1, 2, 3, ...) based on creation order. The database id itself
    is never reused (that would risk mixing up old survey links or ratings),
    but this on-screen number is recalculated fresh each time, so it never
    skips after a delete — delete event #2 and the next new event becomes
    #2 again, event #3 becomes #2, and so on. Computed from every event
    (not just whatever subset a screen is showing), so the same event shows
    the same number everywhere."""
    ordered = sorted(db.list_events(), key=lambda e: e["id"])
    return {e["id"]: i + 1 for i, e in enumerate(ordered)}


# ============================================================================
# Public "fill in the survey" view — reached via a direct link, no nav shown
# ============================================================================
def render_survey_response():
    qp = st.query_params
    try:
        event_id = int(qp.get("event", ""))
    except (TypeError, ValueError):
        st.error("This survey link looks incomplete. Ask the organizer to resend it.")
        return
    person = qp.get("person", "")
    event = db.get_event(event_id)
    if not event:
        st.error("Couldn't find that event. Ask the organizer to resend the link.")
        return

    st.title("🏅 Rate this Team Building")
    st.subheader(f"{event['activity']} — {event['planned_date']}")
    st.caption(f"Organized by {event['organizer']}.")
    if not person:
        participants = [p for p in (event["participants"] or "").split(",") if p]
        person = st.selectbox("Your name (so your rating gets counted)", participants,
                               index=None, placeholder="Choose your name...")
    else:
        st.caption(f"Answering as **{person}**.")
    st.write("Score each question from 1 (not at all) to 5 (completely).")

    with st.form("survey_form"):
        scores = {}
        for cat in db.CATEGORIES:
            scores[cat] = st.slider(db.CATEGORY_LABELS[cat], 1, 5, 3)
        submitted = st.form_submit_button("Submit my rating", use_container_width=True)

    if submitted:
        if not person:
            st.warning("Choose your name above so your rating gets counted, then submit again.")
        else:
            db.record_response(event_id, person, scores)
            st.success("Thanks! Your rating has been recorded.")
            st.balloons()


# ============================================================================
# Overview
# ============================================================================
def render_overview():
    st.title("🎉 Klareco Team Building")
    st.caption("Structure & principles, planning, and scores — all in one place.")

    today = datetime.date.today()
    current_month_value = f"{today.year}-{today.month:02d}"
    if not db.month_has_event(current_month_value):
        next_month_first = (datetime.date(today.year + 1, 1, 1) if today.month == 12
                             else datetime.date(today.year, today.month + 1, 1))
        days_left = (next_month_first - today).days
        st.error(
            f"⚠️ No team building planned for **{today.strftime('%B %Y')}** yet — "
            f"{days_left} day{'s' if days_left != 1 else ''} left in the month. "
            f"Head to **Plan / Edit Event** to lock one in."
        )

    events = db.list_events()
    upcoming = [e for e in events if e["status"] != "Done"]
    upcoming.sort(key=lambda e: e["planned_date"])

    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("Next up")
        if upcoming:
            e = upcoming[0]
            duration = format_duration(e["duration_hours"])
            st.markdown(
                f"**{e['activity'] or '(activity not set yet)'}** — "
                f"{e['planned_date']} {e['start_time'] or ''}"
                f"{f' ({duration})' if duration else ''}\n\n"
                f"Organizer: **{e['organizer']}**  ·  Status: {status_badge(e['status'])}"
            )
            if e["location"]:
                st.caption(f"📍 {e['location']}")
        else:
            st.info("No event planned yet — head to **Plan / Edit Event**.")

    with col2:
        st.subheader("Whose turn is next?")
        st.metric("Next organizer", db.get_next_organizer())

    st.divider()
    st.subheader("The Ground Rules")
    st.markdown(GROUND_RULES)


# ============================================================================
# Plan / Edit Event
# ============================================================================
def render_plan_event():
    st.title("📅 Plan / Edit Team Building")

    events = db.list_events()
    team = [t["name"] for t in db.list_team_members()]
    numbers = event_numbers()

    mode = st.radio("What do you want to do?", ["Create a new event", "Edit an existing event"],
                     horizontal=True)

    if mode == "Edit an existing event":
        if not events:
            st.info("No events yet — create one first.")
            return
        labels = [f"#{numbers[e['id']]} · {e['planned_date']} · {e['activity'] or '(no activity yet)'}"
                  for e in events]
        idx = st.selectbox("Choose an event", range(len(events)), format_func=lambda i: labels[i])
        event = events[idx]
    else:
        event = None

    month_labels, month_values = zip(*db.month_options())
    month_default_idx = month_values.index(event["month"]) if event and event["month"] in month_values else 0
    month_label = st.selectbox("Month", month_labels, index=month_default_idx,
                                key=f"month_{event['id'] if event else 'new'}")
    month_value = dict(zip(month_labels, month_values))[month_label]

    month_year, month_num = int(month_value[:4]), int(month_value[5:7])
    suggested_date = db.first_monday(month_year, month_num)
    # Keep the event's own date while its month hasn't changed; snap to the
    # newly picked month's first Monday otherwise. The dynamic key below is
    # what makes the widget pick up this new default when the month changes.
    default_date = (datetime.date.fromisoformat(event["planned_date"])
                     if event and event["month"] == month_value else suggested_date)

    with st.form("event_form"):
        c1, c2 = st.columns(2)
        with c1:
            planned_date = st.date_input("Planned date (defaults to the 1st Monday)", value=default_date,
                                          key=f"planned_date_{event['id'] if event else 'new'}_{month_value}")
            if planned_date.weekday() != 0:
                st.caption("⚠️ Heads up — this date isn't a Monday.")

            start_time = st.text_input("Start time", value=event["start_time"] if event else "18:00")
            duration_hours = st.number_input(
                "Estimated duration (hours)", min_value=0.0, step=0.5,
                value=float(event["duration_hours"] or 0) if event and event["duration_hours"] else 2.0,
            )

            organizer_default = event["organizer"] if event else db.get_next_organizer()
            organizer = st.selectbox("Organizer", team,
                                      index=team.index(organizer_default) if organizer_default in team else 0)
        with c2:
            activity = st.text_area("Activity description",
                                     value=event["activity"] if event else "",
                                     placeholder="e.g. Bowling night at Bowling Namur, then drinks nearby.")
            location = st.text_input("Location", value=event["location"] if event else "")
            cost = st.number_input("Estimated cost per person (€)", min_value=0.0, step=1.0,
                                    value=float(event["cost_per_person"] or 0) if event else 0.0)
            participants_default = event["participants"].split(",") if event and event["participants"] else team
            participants = st.multiselect("Participants", team,
                                           default=[p for p in participants_default if p in team])

        submitted = st.form_submit_button("Save event", use_container_width=True)

    if submitted:
        if event:
            db.update_event(event["id"], month=month_value, planned_date=planned_date.isoformat(),
                             start_time=start_time, duration_hours=duration_hours, organizer=organizer,
                             activity=activity, location=location, cost_per_person=cost,
                             participants=participants)
            st.success("Event updated.")
        else:
            new_id = db.create_event(month_value, planned_date.isoformat(), start_time, organizer,
                                      activity, location, cost, participants,
                                      duration_hours=duration_hours)
            new_number = event_numbers()[new_id]
            st.success(f"Event #{new_number} created. Head to **Send Invites** when you're ready.")
        st.rerun()

    if event:
        st.divider()
        with st.expander("🗑️ Delete this event"):
            st.warning(
                f"This permanently deletes event #{numbers[event['id']]} "
                f"({event['activity'] or 'no activity set'}, {event['planned_date']}) along with any "
                f"ratings already submitted for it. This can't be undone."
            )
            confirm = st.checkbox("Yes, I'm sure — delete it", key=f"confirm_delete_{event['id']}")
            if st.button("Delete event", type="primary", disabled=not confirm,
                         key=f"delete_btn_{event['id']}", use_container_width=True):
                db.delete_event(event["id"])
                st.success("Event deleted.")
                st.rerun()


# ============================================================================
# Organizer Rotation
# ============================================================================
def render_organizer_rotation():
    st.title("🔁 Organizer Rotation")
    st.caption("Who's up next, and after that. Drag a name below to change the order.")

    team = [t["name"] for t in db.list_team_members()]
    if not team:
        st.info("Add team members on **Team Settings** first.")
        return

    n_months = min(6, len(team) * 2) or 6
    months = db.month_options(n_months)
    queue = db.get_rotation_queue()

    slots = list(zip(months, queue))

    for i, ((label, _value), organizer) in enumerate(slots):
        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 3, 1])
            c1.markdown(f"**{label}**")
            c2.markdown(f"### {organizer}")
            if i == 0:
                c3.markdown("🎯 **Next up**")

    st.divider()
    st.subheader("Reorder the queue")
    st.caption("Drag a name to a new spot — position 1 lines up with the soonest month above.")

    sortable_style = """
    .sortable-component { background-color: transparent; }
    .sortable-container { background-color: transparent; }
    .sortable-item {
        background-color: rgb(240, 242, 246);
        color: rgb(49, 51, 63);
        border: 1px solid rgba(49, 51, 63, 0.2);
        border-radius: 0.5rem;
        font-weight: 600;
    }
    """
    reordered = sort_items(
        queue, direction="vertical", custom_style=sortable_style, key="rotation_queue"
    )
    if reordered != queue:
        db.set_rotation_queue(reordered)
        st.rerun()

    st.divider()
    if st.button("Reset rotation to team order"):
        db.set_rotation_queue(team)
        st.success("Rotation reset.")
        st.rerun()


# ============================================================================
# Send Invites
# ============================================================================
def render_send_invites():
    st.title("✉️ Send Invites")

    events = [e for e in db.list_events() if e["status"] != "Done"]
    if not events:
        st.info("No upcoming events. Plan one first.")
        return

    numbers = event_numbers()
    labels = [f"#{numbers[e['id']]} · {e['planned_date']} · {e['activity'] or '(no activity yet)'}"
              for e in events]
    idx = st.selectbox("Choose an event", range(len(events)), format_func=lambda i: labels[i])
    event = events[idx]
    emails = team_email_map()

    participants = [p for p in (event["participants"] or "").split(",") if p]
    to_list = [emails.get(p) for p in participants if emails.get(p)]
    st.write(f"**Recipients:** {', '.join(participants) or '(none selected — edit the event to add participants)'}")

    duration = format_duration(event["duration_hours"])
    subject = f"Team Building - {event['activity'] or 'this month'} ({event['planned_date']})"
    body_text = (
        f"Hi team,\n\n"
        f"Here's the plan for this month's team building:\n\n"
        f"Activity: {event['activity'] or 'TBC'}\n"
        f"Date: {event['planned_date']} at {event['start_time'] or 'TBC'}\n"
        f"Estimated duration: {duration or 'TBC'}\n"
        f"Location: {event['location'] or 'TBC'}\n"
        f"Organizer: {event['organizer']}\n\n"
        f"See you there!\n{event['organizer']}"
    )

    st.text_area("Email preview — feel free to tweak the wording before sending", body_text, height=220,
                 key=f"invite_preview_{event['id']}")

    st.link_button("📧 Open this email in my email app", mailto_url(to_list, subject, body_text),
                    type="primary", use_container_width=True, disabled=not to_list)
    st.caption("Opens your normal email program (Outlook, Gmail, etc.) with everything filled in — "
               "just check it and hit Send there.")

    if st.button("✅ I've sent it", use_container_width=True):
        db.mark_invites_sent(event["id"])
        st.success("Marked as sent.")
        st.rerun()

    with st.expander("Advanced: have the app send it automatically instead"):
        st.caption("Only needed if you don't want to click Send yourself — requires email setup, see README.md.")
        body_html = "<br>".join(body_text.split("\n"))
        if st.button("Send invites automatically", use_container_width=True):
            sent, detail = emailer.send_email(to_list, subject, body_html, body_text)
            if sent:
                db.mark_invites_sent(event["id"])
                st.success(detail)
            else:
                st.warning("Not sent — email isn't configured. Here's what would have been sent:")
                st.code(detail)


# ============================================================================
# Send Rating Survey
# ============================================================================
def render_send_survey():
    st.title("🏅 Send Rating Survey")

    events = db.list_events()
    if not events:
        st.info("No events yet.")
        return

    numbers = event_numbers()
    labels = [f"#{numbers[e['id']]} · {e['planned_date']} · {e['activity'] or '(no activity yet)'}"
              for e in events]
    idx = st.selectbox("Choose an event", range(len(events)), format_func=lambda i: labels[i])
    event = events[idx]
    emails = team_email_map()
    participants = [p for p in (event["participants"] or "").split(",") if p]
    to_list = [emails.get(p) for p in participants if emails.get(p)]

    responses = db.get_responses(event["id"])
    responded = {r["respondent"] for r in responses}
    st.write(f"**Responses so far:** {len(responded)} / {len(participants)}")
    if participants:
        st.progress(len(responded) / len(participants) if participants else 0)
        st.caption("Responded: " + (", ".join(sorted(responded)) or "—") +
                   "  |  Still waiting on: " + (", ".join(sorted(set(participants) - responded)) or "—"))

    if links_are_local():
        st.warning(
            "⚠️ The rating link currently points to **localhost**, which only works on this "
            "computer — participants won't be able to open it. Deploy the app (see README.md) "
            "and set `APP_BASE_URL` to its real address to fix this."
        )

    link = respond_link(event["id"])
    subject = f"Quick rating: {event['activity'] or 'last team building'}"
    body_text = (
        f"Hi team,\n\n"
        f"Thanks for joining the team building on {event['planned_date']}! "
        f"Got 30 seconds to rate it? Just pick your name from the list when you open the form.\n\n"
        f"{link}\n\nThanks!\n{event['organizer']}"
    )

    st.text_area("Email preview — feel free to tweak the wording before sending", body_text, height=200,
                 key=f"survey_preview_{event['id']}")

    st.link_button("📧 Open this email in my email app", mailto_url(to_list, subject, body_text),
                    type="primary", use_container_width=True, disabled=not to_list)
    st.caption("Everyone gets the same link and just picks their own name from the list — "
               "no need to send separate emails.")

    if st.button("✅ I've sent it", use_container_width=True):
        db.mark_survey_sent(event["id"])
        st.success("Marked as sent.")
        st.rerun()

    with st.expander("Advanced: have the app send personalized links automatically instead"):
        st.caption("Sends each participant their own pre-filled link — requires email setup, see README.md.")
        if st.button("Send personalized rating survey automatically", use_container_width=True):
            results = []
            for p in participants:
                personal_link = respond_link(event["id"], p)
                body_text_p = (
                    f"Hi {p},\n\n"
                    f"Thanks for joining the team building on {event['planned_date']}! "
                    f"Got 30 seconds to rate it?\n\n{personal_link}\n\nThanks!\n{event['organizer']}"
                )
                body_html_p = "<br>".join(body_text_p.split("\n")) + f'<br><br><a href="{personal_link}">Rate it here</a>'
                sent, detail = emailer.send_email([emails.get(p)], subject, body_html_p, body_text_p)
                results.append((p, sent, detail))

            any_sent = any(r[1] for r in results)
            if any_sent:
                db.mark_survey_sent(event["id"])
            for p, sent, detail in results:
                if sent:
                    st.success(f"{p}: sent.")
                else:
                    st.warning(f"{p}: not sent — email isn't configured.")
                    st.code(detail)

    st.divider()
    st.caption("Testing the scoring? Fill in a response yourself here:")
    with st.expander("Fill in a test response"):
        test_person = st.selectbox("As", participants or ["(no participants)"], key="test_person")
        cols = st.columns(4)
        vals = {}
        for c, cat in zip(cols, db.CATEGORIES):
            vals[cat] = c.slider(cat.replace("_", " ").title(), 1, 5, 3, key=f"test_{cat}")
        if st.button("Submit test response"):
            db.record_response(event["id"], test_person, vals)
            st.success("Recorded.")
            st.rerun()


# ============================================================================
# Past Events & Scores
# ============================================================================
def render_past_events():
    st.title("📊 Past Events & Scores")

    events = db.list_events()
    if not events:
        st.info("No events logged yet.")
        return

    rows = []
    for e in events:
        scores = db.get_event_scores(e["id"]) or {}
        rows.append({
            "Date": e["planned_date"],
            "Activity": e["activity"],
            "Organizer": e["organizer"],
            "Status": e["status"],
            "Participants": len([p for p in (e["participants"] or "").split(",") if p]),
            "Responses": scores.get("n_responses", 0),
            "Creativity": scores.get("creativity"),
            "Team Spirit": scores.get("team_spirit"),
            "Fun": scores.get("fun"),
            "Execution": scores.get("execution"),
            "Total": scores.get("total"),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("🏆 Year-End Leaderboard")
    year = st.number_input("Year", value=datetime.date.today().year, step=1)
    board = db.get_leaderboard(year)
    if board:
        st.dataframe(board, use_container_width=True, hide_index=True)
        st.success(f"Reigning champion for {year}: **{board[0]['organizer']}** "
                   f"(avg score {board[0]['avg_score']})")
    else:
        st.info("Not enough rated events yet for this year.")


# ============================================================================
# Team Settings
# ============================================================================
def render_team_settings():
    st.title("👥 Team Settings")
    st.caption("Add, remove, or update the team roster used for rotation, invites, and surveys.")

    members = db.list_team_members()
    for i, m in enumerate(members):
        c0, c1, c2, c3 = st.columns([0.8, 2, 3, 1])
        up, down = c0.columns(2)
        if up.button("⬆️", key=f"up_{m['name']}", disabled=(i == 0)):
            db.move_team_member(m["name"], -1)
            st.rerun()
        if down.button("⬇️", key=f"down_{m['name']}", disabled=(i == len(members) - 1)):
            db.move_team_member(m["name"], 1)
            st.rerun()
        name = c1.text_input("Name", value=m["name"], key=f"name_{m['name']}", disabled=True)
        email = c2.text_input("Email", value=m["email"] or "", key=f"email_{m['name']}")
        if c3.button("Save", key=f"save_{m['name']}"):
            db.upsert_team_member(m["name"], email)
            st.success(f"Updated {m['name']}.")
        if c3.button("Remove", key=f"remove_{m['name']}"):
            db.delete_team_member(m["name"])
            st.rerun()

    st.divider()
    with st.form("add_member"):
        c1, c2, c3 = st.columns([2, 3, 1])
        new_name = c1.text_input("New team member name")
        new_email = c2.text_input("Email")
        add = c3.form_submit_button("Add")
    if add and new_name:
        db.upsert_team_member(new_name, new_email)
        st.rerun()

    st.divider()
    st.subheader("Backup")
    st.caption(
        "Data now lives in Supabase, which keeps its own backups — this is just an extra copy in "
        "your own hands if you ever want one."
    )
    backup_json = json.dumps(db.export_all_data(), indent=2, default=str)
    st.download_button("⬇️ Download a backup (JSON)", backup_json,
                        file_name=f"team_building_backup_{datetime.date.today().isoformat()}.json",
                        mime="application/json", use_container_width=True)


# ============================================================================
# Router
# ============================================================================
qp = st.query_params
if qp.get("respond") == "1":
    render_survey_response()
else:
    page = st.sidebar.radio(
        "Navigate",
        ["🏠 Overview", "📅 Plan / Edit Event", "🔁 Organizer Rotation", "✉️ Send Invites",
         "🏅 Send Rating Survey", "📊 Past Events & Scores", "👥 Team Settings"],
    )
    if page == "🏠 Overview":
        render_overview()
    elif page == "📅 Plan / Edit Event":
        render_plan_event()
    elif page == "🔁 Organizer Rotation":
        render_organizer_rotation()
    elif page == "✉️ Send Invites":
        render_send_invites()
    elif page == "🏅 Send Rating Survey":
        render_send_survey()
    elif page == "📊 Past Events & Scores":
        render_past_events()
    elif page == "👥 Team Settings":
        render_team_settings()
