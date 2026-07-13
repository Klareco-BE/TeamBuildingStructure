"""
Klareco Team Building — standalone dashboard.

Run locally:      streamlit run app.py
Data lives in:     team_building.db (SQLite, created automatically)
Email setup:       copy .env.example to .env and fill in your SMTP details
                    (see README.md). Until then, "send" buttons show a
                    preview of the email instead of actually sending it.
"""
import datetime
import urllib.parse

import streamlit as st

import db
import emailer

st.set_page_config(page_title="Klareco Team Building", page_icon="🎉", layout="wide")
db.init_db()

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
    import os
    return os.getenv("APP_BASE_URL", "http://localhost:8501")


def respond_link(event_id, person):
    params = urllib.parse.urlencode({"respond": "1", "event": event_id, "person": person})
    return f"{base_url()}/?{params}"


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
    st.caption(f"Organized by {event['organizer']}. Answering as **{person or 'you'}**.")
    st.write("Score each question from 1 (not at all) to 5 (completely).")

    with st.form("survey_form"):
        scores = {}
        for cat in db.CATEGORIES:
            scores[cat] = st.slider(db.CATEGORY_LABELS[cat], 1, 5, 3)
        submitted = st.form_submit_button("Submit my rating", use_container_width=True)

    if submitted:
        respondent = person or st.session_state.get("fallback_name", "")
        if not respondent:
            st.warning("We couldn't tell who you are from the link — enter your name below and resubmit.")
            respondent = st.text_input("Your name")
        if respondent:
            db.record_response(event_id, respondent, scores)
            st.success("Thanks! Your rating has been recorded.")
            st.balloons()


# ============================================================================
# Overview
# ============================================================================
def render_overview():
    st.title("🎉 Klareco Team Building")
    st.caption("Structure & principles, planning, and scores — all in one place.")

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

    mode = st.radio("What do you want to do?", ["Create a new event", "Edit an existing event"],
                     horizontal=True)

    if mode == "Edit an existing event":
        if not events:
            st.info("No events yet — create one first.")
            return
        labels = [f"#{e['id']} · {e['planned_date']} · {e['activity'] or '(no activity yet)'}" for e in events]
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
            st.success(f"Event #{new_id} created. Head to **Send Invites** when you're ready.")
        st.rerun()


# ============================================================================
# Organizer Rotation
# ============================================================================
def render_organizer_rotation():
    st.title("🔁 Organizer Rotation")
    st.caption("Who's up next, and after that. Reassign a month and the rest of the queue shifts to fit.")

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
    st.subheader("Reassign a month")
    st.caption("Pick the month someone wants to (re)organize, and who should take it. "
               "Everyone in between slides over by one.")

    with st.form("reassign_organizer"):
        c1, c2 = st.columns(2)
        month_idx = c1.selectbox("Month", range(len(slots)), format_func=lambda i: slots[i][0][0])
        new_organizer = c2.selectbox("New organizer", team)
        submitted = st.form_submit_button("Update rotation", use_container_width=True)

    if submitted:
        db.move_organizer_to_slot(new_organizer, month_idx)
        st.success(f"{new_organizer} now organizes {slots[month_idx][0][0]}. The rest of the queue shifted.")
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

    labels = [f"#{e['id']} · {e['planned_date']} · {e['activity'] or '(no activity yet)'}" for e in events]
    idx = st.selectbox("Choose an event", range(len(events)), format_func=lambda i: labels[i])
    event = events[idx]
    emails = team_email_map()

    participants = [p for p in (event["participants"] or "").split(",") if p]
    st.write(f"**Recipients:** {', '.join(participants) or '(none selected — edit the event to add participants)'}")

    duration = format_duration(event["duration_hours"])
    subject = f"Team Building — {event['activity'] or 'this month'} ({event['planned_date']})"
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
    body_html = "<br>".join(body_text.split("\n"))

    st.text_area("Email preview", body_text, height=220)

    if st.button("Send invites now", type="primary", use_container_width=True):
        to_list = [emails.get(p) for p in participants if emails.get(p)]
        sent, detail = emailer.send_email(to_list, subject, body_html, body_text)
        if sent:
            db.mark_invites_sent(event["id"])
            st.success(detail)
        else:
            st.warning("Not sent as a real email yet — showing what would be sent:")
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

    labels = [f"#{e['id']} · {e['planned_date']} · {e['activity'] or '(no activity yet)'}" for e in events]
    idx = st.selectbox("Choose an event", range(len(events)), format_func=lambda i: labels[i])
    event = events[idx]
    emails = team_email_map()
    participants = [p for p in (event["participants"] or "").split(",") if p]

    responses = db.get_responses(event["id"])
    responded = {r["respondent"] for r in responses}
    st.write(f"**Responses so far:** {len(responded)} / {len(participants)}")
    if participants:
        st.progress(len(responded) / len(participants) if participants else 0)
        st.caption("Responded: " + (", ".join(sorted(responded)) or "—") +
                   "  |  Still waiting on: " + (", ".join(sorted(set(participants) - responded)) or "—"))

    st.markdown("Each participant gets their own personal link so their answer is tracked correctly.")

    if st.button("Send rating survey now", type="primary", use_container_width=True):
        results = []
        for p in participants:
            link = respond_link(event["id"], p)
            subject = f"Quick rating: {event['activity'] or 'last team building'}"
            body_text = (
                f"Hi {p},\n\n"
                f"Thanks for joining the team building on {event['planned_date']}! "
                f"Got 30 seconds to rate it?\n\n{link}\n\nThanks!\n{event['organizer']}"
            )
            body_html = "<br>".join(body_text.split("\n")) + f'<br><br><a href="{link}">Rate it here</a>'
            sent, detail = emailer.send_email([emails.get(p)], subject, body_html, body_text)
            results.append((p, sent, detail))

        any_sent = any(r[1] for r in results)
        if any_sent:
            db.mark_survey_sent(event["id"])
        for p, sent, detail in results:
            if sent:
                st.success(f"{p}: sent.")
            else:
                st.warning(f"{p}: not sent as real email — preview below.")
                st.code(detail)

    st.divider()
    st.caption("Testing without email set up? Fill in a response yourself here:")
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
    for m in members:
        c1, c2, c3 = st.columns([2, 3, 1])
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
