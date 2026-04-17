"""Streamlit screens — login, intake form, chat, report.

The chat screen is the interesting one: every Streamlit rerun it decides
whether the graph needs to run another turn (e.g., phase kicked off but Alex
hasn't spoken yet) or whether to wait for user input. The UI is thin — all
interview logic lives in the graph.
"""

import json
from datetime import date
from pathlib import Path

import streamlit as st

from app.config import APP_PASSWORD, APP_USERNAME
from app.graph.graph import invoke_turn
from app.graph.state import new_state
from app.services import candidate, llm
from app.ui.components import DRIVER_BADGES, car_indicators, driver_badge, probe_badge

_DRIVER_PHASES = {"thinking", "action", "people", "mastery"}


def _extract_mastery_question(jd: str) -> str:
    """Take the last non-empty line of the JD as the mastery question."""
    lines = [l.strip() for l in jd.strip().splitlines() if l.strip()]
    return lines[-1] if lines else "Tell me about a time you delivered a project end-to-end."


def _merged_car_up_to(history: list[dict], idx: int) -> dict | None:
    """OR-merge all car_judge entries for the same phase, up to and including
    the verdict for the user message at `idx`. This way badges show accumulated
    progress — once context is true, it stays green even if later answers
    don't repeat it."""
    # Find the phase of this user message.
    phase = history[idx].get("phase")
    if not phase:
        return None

    # Merge all car_judge entries for this phase up to the one after idx.
    merged = None
    for entry in history[:idx + 5]:  # look a few entries past idx for the verdict
        if entry.get("role") == "car_judge" and entry.get("phase") == phase:
            car = entry.get("car", {})
            if merged is None:
                merged = {"context": False, "action": False, "result": False}
            for k in ("context", "action", "result"):
                if car.get(k):
                    merged[k] = True
    return merged


def init_state():
    if "started" not in st.session_state:
        st.session_state.started = False
    if "graph_state" not in st.session_state:
        st.session_state.graph_state = None
    if "demo_mode" not in st.session_state:
        st.session_state.demo_mode = False
    if "driver_levels" not in st.session_state:
        st.session_state.driver_levels = {}
    if "report" not in st.session_state:
        st.session_state.report = None


def show_login():
    st.title("🔐 ProofDrive Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login", type="primary"):
        if username == APP_USERNAME and password == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Invalid username or password.")


def show_intake_form():
    st.title("🎯 ProofDrive Interview")
    st.caption("Answer honestly. Speak naturally. Take your time.")

    experience = st.selectbox(
        "Experience Level",
        ["Fresh Graduate (FG)", "1–2 Years (EXP)", "3–5 Years (EXP)"],
    )
    role = "Business Analyst"
    st.markdown("**Target Role:** Business Analyst")

    JD = """Technical Business Analyst - SAS (Statistical Analysis System)
Client Name: Texas Comptroller of Public Accounts
Position Working Title: Technical Business Analyst
C2C Rate: $65/Hr C2C | Estimated Start Date: 07/16/24
Location: ON-SITE — Austin, TX or surrounding areas (max 1–2 hr drive)

HOW WE CAN CLOSE THE POSITION:
- Experience with SAS (Statistical Analytical System) programming: Minimum 5 Years
- Experience with Oracle (18+) data warehousing development: Minimum 5 Years
- Experience with Oracle database programming (SQL, TSQL, PL/SQL, BTEQ): Minimum 5 Years
- Public sector experience (Federal, State or Local Government): Minimum 5 Years

DESCRIPTION OF JOB DUTIES:
As a Technical Business Analyst, the candidate must align information technology systems with business operations by analyzing, recommending, and developing innovative reporting solutions. The candidate will work with IT and Business resources to discover, analyze, and inventory legacy reports including SAS routines. The position requires the ability to clearly document and communicate processes/requirements to both Business and Technical resources.

Duties include:
- Coordinate and facilitate business collaborator meetings to discover, analyze, inventory, and document legacy reports including SAS routines
- Assist in the evaluation of technical solutions and make recommendations based on sound software development processes
- Prepare detailed technical documentation and generate work estimates in an SDLC environment
- Interact with product owners, internal/external collaborators, and Business Intelligence/Data Warehouse staff
- Provide guidance and knowledge sharing to existing development staff

Work Location: 111 E 17th Street, Austin, Texas 78711
Work Hours: 8:00 AM – 5:00 PM

REQUIREMENTS:
- Expertise in requirement gathering, customer engagement, and project management
- Experience with data warehousing design/development
- Experience with SAS (Statistical Analytical System) programming
- Experience with data warehouse architecture standards, data integration, data quality, multi-dimensional design, and ETL tools
- Experience with Oracle (18+) data warehousing development
- Experience with Oracle database programming (SQL, TSQL, PL/SQL, BTEQ)
- Public sector experience (Federal, State or Local Government)
- Agile/Scrum and Kanban experience
- Proficient with Microsoft Office (Outlook, Teams, Project, Word, Visio, Excel, PowerPoint)
- Strong written, verbal, and interpersonal communication skills

Pay: $60.00 – $65.00 per hour | Contract | 8-hour shift"""

    jd = JD
    with st.expander("📄 Job Description", expanded=False):
        st.text(JD)
    demo_mode = st.checkbox(
        "Demo Mode",
        help="Candidate answers are generated automatically. Press the button in the interview to advance.",
    )
    driver_levels = {}
    if demo_mode:
        st.markdown("**Create Your Own Candidate**")
        st.caption("Set the target level (1-5) for each driver. The simulated candidate will answer at exactly these levels.")
        col_t, col_a, col_p, col_m = st.columns(4)
        with col_t:
            driver_levels["thinking"] = st.slider("Thinking", 1, 5, 3, key="sl_thinking")
        with col_a:
            driver_levels["action"] = st.slider("Action", 1, 5, 3, key="sl_action")
        with col_p:
            driver_levels["people"] = st.slider("People", 1, 5, 3, key="sl_people")
        with col_m:
            driver_levels["mastery"] = st.slider("Mastery", 1, 5, 3, key="sl_mastery")

        # Candidate strength indicator — small badge aligned to the right.
        avg = sum(driver_levels.values()) / 4
        if avg >= 4.5:
            label, color, emoji = "Star", "#FFD700", "⭐"
        elif avg >= 3.5:
            label, color, emoji = "Strong", "#28A745", "💪"
        elif avg >= 2.5:
            label, color, emoji = "Average", "#FF8C00", "😐"
        elif avg >= 1.5:
            label, color, emoji = "Weak", "#DC3545", "😟"
        else:
            label, color, emoji = "Very Weak", "#8B0000", "😵"

        pct = (avg - 1) / 4 * 100
        st.markdown(
            f'<div style="display:flex;justify-content:flex-end;margin-top:8px">'
            f'<div style="padding:6px 14px;background:#1a1a2e;border-radius:8px;display:inline-flex;align-items:center;gap:10px">'
            f'<div style="width:150px;background:#2a2a3e;border-radius:4px;height:6px;overflow:hidden">'
            f'<div style="background:{color};width:{pct}%;height:6px;border-radius:4px"></div>'
            f'</div>'
            f'<span style="color:{color};font-size:12px;font-weight:600">{emoji} {label}</span>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if st.button("▶ Start Interview", type="primary"):
        mode = "FG" if "FG" in experience else "EXP"

        config = {
            "mode": mode,
            "role": role.strip(),
            "job_description": jd.strip(),
            "mastery_question": _extract_mastery_question(jd),
        }
        state = new_state(config)

        # Kick off the interview — orchestrator sees empty history and picks intro_agent.
        try:
            with st.spinner("Starting interview..."):
                state = invoke_turn(state)
        except Exception as e:
            st.error(f"Could not reach the interview model. Check the server is running. ({e})")
            return

        st.session_state.graph_state = state
        st.session_state.started = True
        st.session_state.demo_mode = demo_mode
        st.session_state.driver_levels = driver_levels
        llm.reset_tokens()
        st.rerun()


def show_chat_screen():
    state = st.session_state.graph_state

    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("💬 Interview in Progress")
    with col2:
        st.markdown(f"**Phase:** `{state.get('phase', 'intro').capitalize()}`")

    st.divider()

    # Render history. Three entry types show up inline:
    #   - assistant / user → chat bubbles
    #   - orchestrator → a tight "Show reasoning" expander that surfaces the
    #     LLM's decision + rationale (collapsed by default)
    # car_judge entries don't get their own bubble; we render CAR badges
    # underneath the preceding user message.
    for idx, msg in enumerate(state["history"]):
        role = msg.get("role")
        if role == "assistant":
            with st.chat_message("assistant", avatar="🎙"):
                badge_phase = msg.get("phase")
                if badge_phase in DRIVER_BADGES:
                    label, color = DRIVER_BADGES[badge_phase]
                    driver_badge(label, color)
                probe = msg.get("probe_for")
                if probe:
                    probe_badge(probe)
                st.markdown(f"**Alex:** {msg['content']}")
        elif role == "user":
            with st.chat_message("user", avatar="👤"):
                st.markdown(msg["content"])
                car = _merged_car_up_to(state["history"], idx)
                if car:
                    car_indicators(car)
        elif role == "orchestrator":
            # Slim, collapsed-by-default expander — shows up as a faint line with
            # an arrow. Click to see what the orchestrator decided and why.
            action = msg.get("next_action", "?")
            reason = msg.get("reason", "")
            phase_at = msg.get("phase", "?")
            with st.expander(f"💭 Show reasoning — decided `{action}`", expanded=False):
                st.markdown(
                    f"**Decision:** `{action}`  \n"
                    f"**Phase at decision:** `{phase_at}`  \n"
                    f"**Reasoning:** {reason}"
                )
        # car_judge entries are not rendered as chat bubbles.

    # If report is ready, show it.
    if state.get("final_report"):
        st.session_state.report = state["final_report"]
        show_report_screen(state, state["final_report"])
        return

    # If phase is 'done' but report not yet compiled, nudge the graph.
    if state.get("phase") == "done" and state.get("final_report") is None:
        with st.spinner("Generating your ProofDrive report..."):
            state = invoke_turn(state)
            st.session_state.graph_state = state
        st.rerun()
        return

    # After close_agent has delivered its message, automatically advance to
    # report generation — no user input needed, just like a real interview
    # where the interviewer says goodbye and then writes the report.
    has_close_message = any(
        m.get("role") == "assistant" and m.get("phase") == "close"
        for m in state["history"]
    )
    if has_close_message and state.get("final_report") is None:
        try:
            with st.spinner("Preparing your ProofDive report..."):
                # Keep invoking until the report is populated.
                while state.get("final_report") is None:
                    state = invoke_turn(state)
        except Exception as e:
            st.error(f"Could not generate report. ({e})")
            return
        st.session_state.graph_state = state
        st.rerun()
        return

    # If the last history entry is a car_judge entry, the graph needs another
    # turn (orchestrator loops back after car_agent).
    last = state["history"][-1] if state["history"] else None
    if last is None or last.get("role") in ("car_judge",):
        try:
            with st.spinner("Alex is thinking..."):
                state = invoke_turn(state)
        except Exception as e:
            st.error(f"Could not reach the interview model. ({e})")
            return
        st.session_state.graph_state = state
        st.rerun()
        return

    # Collect the candidate's next answer — either typed or demo-generated.
    user_input = None
    if st.session_state.demo_mode:
        if st.button("🎭 Generate Candidate Answer", type="primary"):
            with st.spinner("John is thinking..."):
                # Build prompt with only the targeted competency's rubric.
                prompt = candidate.build_dynamic_prompt(
                    st.session_state.driver_levels,
                    current_competency=state.get("current_competency"),
                    current_phase=state.get("phase"),
                )
                user_input = candidate.generate_answer(
                    [m for m in state["history"] if m.get("role") in ("assistant", "user")],
                    prompt,
                )
    else:
        user_input = st.chat_input("Type your answer here...")

    if user_input:
        # Append the user's answer to history and invoke one more turn.
        # The orchestrator will route to car_agent → (loop back) → next agent.
        state["history"].append({
            "role": "user",
            "phase": state.get("phase", "intro"),
            "content": user_input,
        })
        try:
            with st.spinner("Alex is thinking..."):
                state = invoke_turn(state)
        except Exception as e:
            st.error(f"Could not reach the interview model. Please try again. ({e})")
            state["history"].pop()
            st.stop()
        st.session_state.graph_state = state
        st.rerun()

    if st.button("✕ End Interview", type="secondary"):
        st.session_state.started = False
        st.session_state.graph_state = None
        st.rerun()


def _label_color(label: str) -> str:
    return {"Star": "#FFD700", "Ready": "#28A745", "Borderline": "#FF8C00"}.get(label, "#DC3545")


def _status_icon(status: str) -> str:
    if status == "Strong":
        return '<span style="color:#28A745">&#10003; Strong</span>'
    if status == "Partial":
        return '<span style="color:#FF8C00">&#9651; Partial</span>'
    return '<span style="color:#DC3545">&#10007; Weak</span>'


def show_report_screen(state: dict, report: dict) -> None:
    """Render the full ProofDrive AI Interview Report."""
    if report.get("error"):
        st.error(f"Report generation failed: {report.get('message', 'Unknown error')}")
        with st.expander("Raw LLM output"):
            st.code(report.get("raw", ""), language="text")
        _new_interview_button()
        return

    cfg = state["config"]
    today = date.today().strftime("%B %d, %Y")

    st.markdown("""<style>
    .rpt td, .rpt th, .rpt li, .rpt p, .rpt b, .rpt small, .rpt span,
    .rpt i, .rpt strong { color: #E0E0E0 !important; }
    </style>""", unsafe_allow_html=True)

    col_logo, col_badge = st.columns([3, 1])
    with col_logo:
        st.markdown('<b style="font-size:24px;color:white">ProofDive</b>', unsafe_allow_html=True)
    with col_badge:
        st.markdown(
            '<div style="text-align:right"><span style="background:#E9ECEF;color:#495057;'
            'padding:4px 12px;border-radius:12px;font-size:12px;font-weight:600">'
            'AI INTERVIEW REPORT</span></div>',
            unsafe_allow_html=True,
        )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown('<div class="rpt"><small style="color:#6C757D">Candidate</small><br><b style="color:white">Candidate</b></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="rpt"><small style="color:#6C757D">Target Role</small><br><b style="color:white">{cfg["role"]}</b></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="rpt"><small style="color:#6C757D">Experience</small><br><b style="color:white">{cfg["mode"]}</b></div>', unsafe_allow_html=True)
    with c4:
        st.markdown('<div class="rpt"><small style="color:#6C757D">Interview Type</small><br><b style="color:white">Role-Based Mock</b></div>', unsafe_allow_html=True)
    st.markdown(f'<small style="color:#6C757D">{today}</small>', unsafe_allow_html=True)
    st.divider()

    overall = report.get("overall_score", 0)
    label = report.get("overall_label", "Not Yet")
    sublabel = report.get("overall_sublabel", "")
    summary = report.get("overall_summary", "")
    badge_color = _label_color(label)
    border_color = "#28A745" if report.get("pass") else "#DC3545"

    st.markdown(
        f'<div style="background:#1a1a2e;border-radius:12px;padding:24px;color:white">'
        f'<div style="display:flex;align-items:center;gap:24px">'
        f'<div style="min-width:100px;height:100px;border-radius:50%;border:4px solid {border_color};'
        f'display:flex;flex-direction:column;align-items:center;justify-content:center">'
        f'<span style="font-size:28px;font-weight:700;color:white">{overall}</span>'
        f'<small style="color:#ADB5BD">out of 5.0</small>'
        f'</div>'
        f'<div>'
        f'<span style="background:{badge_color};color:white;padding:4px 12px;border-radius:12px;'
        f'font-size:13px;font-weight:600">{label}'
        f'{f" — {sublabel}" if sublabel else ""}</span>'
        f'<h3 style="color:white;margin:8px 0">Overall Performance</h3>'
        f'<p style="color:#ADB5BD;margin:0">{summary}</p>'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )

    pass_text = "PASS" if report.get("pass") else "NOT YET"
    pass_icon = "&#10003;" if report.get("pass") else "&#10007;"
    role_model_html = (
        ' &nbsp;|&nbsp; <span style="color:#FFD700">&#9733; Role Model</span>'
        if report.get("role_model") else ""
    )
    st.markdown(
        f'<div style="margin-top:8px;font-size:14px">'
        f'<span style="color:{border_color}">{pass_icon} {pass_text}</span>'
        f'{role_model_html}</div>',
        unsafe_allow_html=True,
    )
    st.divider()

    DRIVER_COLORS = {
        "thinking": "#1E90FF",
        "action": "#28A745",
        "people": "#17A2B8",
        "mastery": "#6F42C1",
    }
    st.markdown(
        '<span style="color:#6C757D;font-size:12px;font-weight:600;letter-spacing:1px">'
        'COMPETENCY BREAKDOWN</span>',
        unsafe_allow_html=True,
    )
    drivers = report.get("drivers", {})
    for drv in ("thinking", "action", "people", "mastery"):
        d = drivers.get(drv, {})
        score = d.get("score", 0)
        color = DRIVER_COLORS.get(drv, "#6C757D")
        sublabel_d = d.get("sublabel", "")
        anchor = d.get("anchor_label", "")
        pct = min(score / 5 * 100, 100)
        st.markdown(
            f'<div class="rpt" style="margin-bottom:12px">'
            f'<b style="text-transform:capitalize;color:white">{drv}</b> '
            f'<small style="color:#6C757D">{sublabel_d}</small>'
            f'<div style="background:#E9ECEF;border-radius:4px;height:8px;margin:6px 0">'
            f'<div style="background:{color};width:{pct}%;height:8px;border-radius:4px"></div>'
            f'</div>'
            f'<div style="display:flex;justify-content:space-between">'
            f'<small style="color:#6C757D">{anchor}</small>'
            f'<b style="color:white">{score}</b>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
    st.divider()

    st.markdown(
        '<span style="color:#6C757D;font-size:12px;font-weight:600;letter-spacing:1px">'
        'CAR ANALYSIS &mdash; CONTEXT &middot; ACTION &middot; RESULT</span>',
        unsafe_allow_html=True,
    )
    car = report.get("car_analysis", {})
    rows = ""
    for elem in ("context", "action", "result"):
        e = car.get(elem, {})
        status = e.get("status", "Weak")
        feedback = e.get("feedback", "")
        rows += (
            f'<tr><td style="padding:8px;font-weight:600;color:white">{elem.capitalize()}</td>'
            f'<td style="padding:8px">{_status_icon(status)}</td>'
            f'<td style="padding:8px;color:white">{feedback}</td></tr>'
        )
    st.markdown(
        f'<table class="rpt" style="width:100%;border-collapse:collapse">'
        f'<tr style="background:#2a2a3e"><th style="padding:8px;text-align:left;color:#ADB5BD">Element</th>'
        f'<th style="padding:8px;text-align:left;color:#ADB5BD">Status</th>'
        f'<th style="padding:8px;text-align:left;color:#ADB5BD">Feedback</th></tr>'
        f'{rows}</table>',
        unsafe_allow_html=True,
    )
    car_insight = report.get("car_insight", "")
    if car_insight:
        st.markdown(
            f'<div style="background:#1a2a3e;border-left:4px solid #17A2B8;padding:12px;'
            f'border-radius:4px;margin-top:12px;color:#ADB5BD"><b>Insight:</b> {car_insight}</div>',
            unsafe_allow_html=True,
        )
    st.divider()

    st.markdown(
        '<span style="color:#6C757D;font-size:12px;font-weight:600;letter-spacing:1px">'
        'STRENGTHS &amp; AREAS FOR IMPROVEMENT</span>',
        unsafe_allow_html=True,
    )
    col_s, col_a = st.columns(2)
    with col_s:
        for s in report.get("strengths", []):
            bullets = "".join(f'<li style="color:white">{b}</li>' for b in s.get("bullets", []))
            st.markdown(
                f'<div class="rpt" style="border-left:4px solid #28A745;padding:12px;margin-bottom:12px;'
                f'background:#1a2e1a;border-radius:4px">'
                f'<b style="color:#28A745">{s.get("title", "")}</b>'
                f'<ul style="margin:4px 0 0 0;padding-left:20px">'
                f'{bullets}</ul></div>',
                unsafe_allow_html=True,
            )
    with col_a:
        for a in report.get("areas", []):
            bullets = "".join(f'<li style="color:white">{b}</li>' for b in a.get("bullets", []))
            fix_html = ""
            if a.get("fix"):
                fix_html += f'<p style="color:#FF8C00;font-style:italic;margin:4px 0"><b>Fix:</b> {a["fix"]}</p>'
            if a.get("instead_of"):
                fix_html += f'<p style="color:#FF8C00;margin:4px 0"><b>Instead of:</b> "{a["instead_of"]}"</p>'
            if a.get("say"):
                fix_html += f'<p style="color:#28A745;margin:4px 0"><b>Say:</b> "{a["say"]}"</p>'
            st.markdown(
                f'<div class="rpt" style="border-left:4px solid #FF8C00;padding:12px;margin-bottom:12px;'
                f'background:#2e2a1a;border-radius:4px">'
                f'<b style="color:#FF8C00">{a.get("title", "")}</b>'
                f'<ul style="margin:4px 0 0 0;padding-left:20px">'
                f'{bullets}</ul>{fix_html}</div>',
                unsafe_allow_html=True,
            )
    st.divider()

    qi_list = report.get("question_insights", [])
    if qi_list:
        st.markdown(
            '<span style="color:#6C757D;font-size:12px;font-weight:600;letter-spacing:1px">'
            'QUESTION-LEVEL INSIGHTS</span>',
            unsafe_allow_html=True,
        )
        for qi in qi_list:
            bullets = ""
            for cb in qi.get("car_bullets", []):
                icon = (
                    '<span style="color:#28A745">&#10003;</span>'
                    if cb.get("status") == "good"
                    else '<span style="color:#FF8C00">&#9651;</span>'
                )
                bullets += f'<li style="color:#ADB5BD">{icon} {cb.get("text", "")}</li>'
            st.markdown(
                f'<div class="rpt" style="background:#1a1a2e;border-radius:8px;padding:16px;margin-bottom:12px">'
                f'<div style="display:flex;justify-content:space-between;align-items:center">'
                f'<i style="color:#ADB5BD">"{qi.get("question", "")}"</i>'
                f'<span style="background:#2a2a3e;color:#ADB5BD;padding:2px 8px;border-radius:8px;font-weight:600">'
                f'{qi.get("score", 0)} / 5</span></div>'
                f'<ul style="margin:8px 0 0 0;padding-left:20px">{bullets}</ul></div>',
                unsafe_allow_html=True,
            )
        st.divider()

    cards = report.get("coaching_cards", [])
    if cards:
        st.markdown(
            '<span style="color:#6C757D;font-size:12px;font-weight:600;letter-spacing:1px">'
            'AI COACHING RECOMMENDATIONS</span>',
            unsafe_allow_html=True,
        )
        for i in range(0, len(cards), 2):
            row_cards = cards[i:i + 2]
            cols = st.columns(2)
            for j, card in enumerate(row_cards):
                bullets = "".join(f'<li style="color:#ADB5BD">&rarr; {b}</li>' for b in card.get("bullets", []))
                cols[j].markdown(
                    f'<div class="rpt" style="background:#1a1a2e;border-radius:8px;padding:16px">'
                    f'<b style="color:white">{card.get("title", "")}</b>'
                    f'<ul style="margin:8px 0 0 0;padding-left:20px">{bullets}</ul></div>',
                    unsafe_allow_html=True,
                )
        st.divider()

    hr = report.get("hiring_readiness", {})
    if hr:
        st.markdown(
            '<span style="color:#6C757D;font-size:12px;font-weight:600;letter-spacing:1px">'
            'HIRING READINESS</span>',
            unsafe_allow_html=True,
        )
        hr_items = [
            ("Technical Readiness", hr.get("technical", {})),
            ("Behavioral Readiness", hr.get("behavioral", {})),
            ("Communication", hr.get("communication", {})),
            ("Interview Readiness", hr.get("interview", {})),
        ]
        row1 = st.columns(2)
        row2 = st.columns(2)
        for idx, (title, data) in enumerate(hr_items):
            col = row1[idx] if idx < 2 else row2[idx - 2]
            positive = data.get("positive", False)
            icon = "&#10003;" if positive else "&#9888;"
            icon_color = "#28A745" if positive else "#FF8C00"
            col.markdown(
                f'<div class="rpt" style="background:#1a1a2e;border-radius:8px;padding:16px;text-align:center">'
                f'<div style="font-size:24px;color:{icon_color}">{icon}</div>'
                f'<div style="font-weight:600;color:white">{title}</div>'
                f'<div style="color:#6C757D">{data.get("rating", "N/A")}</div></div>',
                unsafe_allow_html=True,
            )
        st.divider()

    verdict_title = report.get("final_verdict_title", "")
    verdict_body = report.get("final_verdict_body", "")
    st.markdown(
        f'<div style="background:#1a1a2e;border-radius:12px;padding:24px;color:white">'
        f'<span style="font-size:32px;color:#6C757D">&ldquo;</span>'
        f'<h3 style="color:white">Final Verdict &mdash; {verdict_title}</h3>'
        f'<p style="color:#ADB5BD">{verdict_body}</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;color:#6C757D;font-size:12px;margin-top:16px">'
        f'<span>ProofDive &mdash; Deep Dives Technologies</span><span>{today}</span></div>',
        unsafe_allow_html=True,
    )

    st.divider()
    log = llm.get_token_log()
    # Split the log into "interview" (everything but the final report agent) and
    # "evaluation" (just the report agent). Each summary returns prompt/completion/total/cost.
    interview = llm.summarize_log(log, label_filter=lambda lbl: lbl != "report")
    evaluation = llm.summarize_log(log, label_filter=lambda lbl: lbl == "report")
    grand = llm.summarize_log(log)

    def _token_card(title: str, summary: dict) -> str:
        return (
            f'<div style="background:#1a1a2e;border-radius:8px;padding:16px">'
            f'<div style="color:#ADB5BD;font-size:13px;margin-bottom:8px">{title}</div>'
            f'<div style="display:flex;justify-content:space-between;color:white;font-size:13px">'
            f'<span style="color:#6C757D">Input</span>'
            f'<span style="font-weight:600">{summary["prompt"]:,}</span></div>'
            f'<div style="display:flex;justify-content:space-between;color:white;font-size:13px">'
            f'<span style="color:#6C757D">Output</span>'
            f'<span style="font-weight:600">{summary["completion"]:,}</span></div>'
            f'<div style="display:flex;justify-content:space-between;color:white;font-size:13px;'
            f'border-top:1px solid #2a2a3e;padding-top:6px;margin-top:6px">'
            f'<span style="color:#6C757D">Total</span>'
            f'<span style="font-weight:700">{summary["total"]:,}</span></div>'
            f'<div style="display:flex;justify-content:space-between;color:#28A745;font-size:14px;'
            f'margin-top:8px">'
            f'<span>Cost</span>'
            f'<span style="font-weight:700">${summary["cost_usd"]:.4f}</span></div>'
            f'</div>'
        )

    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        st.markdown(_token_card("Interview", interview), unsafe_allow_html=True)
    with col_t2:
        st.markdown(_token_card("Evaluation", evaluation), unsafe_allow_html=True)
    with col_t3:
        st.markdown(_token_card("Grand Total", grand), unsafe_allow_html=True)

    st.caption("Pricing per model (edit `app/model_config.py` to change)")

    st.download_button(
        "Download token log (JSON)",
        data=json.dumps(log, indent=2),
        file_name="token_log.json",
        mime="application/json",
    )
    _new_interview_button()


def _new_interview_button() -> None:
    if st.button("Start New Interview"):
        st.session_state.started = False
        st.session_state.graph_state = None
        st.session_state.report = None
        st.rerun()
