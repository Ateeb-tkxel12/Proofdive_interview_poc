import streamlit as st

DRIVER_BADGES = {
    "thinking": ("🧠 Power of Thinking", "#1E90FF"),
    "action":   ("⚡ Power of Action",   "#FF8C00"),
    "people":   ("🤝 Power of People",   "#28A745"),
    "mastery":  ("🎯 Power of Mastery",  "#DC3545"),
}

PROBE_COLORS = {
    "context": "#6C757D",
    "action":  "#FF8C00",
    "result":  "#17A2B8",
}

DRIVER_PHASES = {"thinking", "action", "people", "mastery"}


def first_missing(car: dict) -> str | None:
    """Return the first CAR element that is False, in C->A->R order."""
    for element in ("context", "action", "result"):
        if not car.get(element):
            return element
    return None


def driver_badge(label: str, color: str) -> None:
    st.markdown(
        f'<span style="background:{color};color:white;padding:3px 10px;'
        f'border-radius:12px;font-size:12px;font-weight:600">{label}</span>',
        unsafe_allow_html=True,
    )


def probe_badge(element: str) -> None:
    color = PROBE_COLORS.get(element, "#6C757D")
    st.markdown(
        f'<span style="background:{color};color:white;padding:2px 8px;'
        f'border-radius:8px;font-size:11px;font-weight:500">'
        f'Probing for: {element.capitalize()}</span>',
        unsafe_allow_html=True,
    )


def car_indicators(car: dict) -> None:
    """Render indicators only for elements present in car dict."""
    parts = []
    for element in ("context", "action", "result"):
        if element not in car:
            continue
        present = car[element]
        icon = "✅" if present else "❌"
        color = "#28A745" if present else "#DC3545"
        parts.append(f'<span style="font-size:12px;color:{color}">{icon} {element.capitalize()}</span>')
    if parts:
        st.markdown(" &nbsp;&nbsp; ".join(parts), unsafe_allow_html=True)
