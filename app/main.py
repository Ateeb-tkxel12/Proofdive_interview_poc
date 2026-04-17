import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Configure logging BEFORE importing anything else so all modules pick it up.
# Logs go to stderr (Streamlit's terminal), not the browser.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

import streamlit as st

from app.ui.screens import init_state, show_login, show_intake_form, show_chat_screen

st.set_page_config(page_title="ProofDrive Interview", layout="wide")


def main():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        show_login()
        return

    init_state()
    if st.session_state.started:
        show_chat_screen()
    else:
        show_intake_form()


if __name__ == "__main__":
    main()
