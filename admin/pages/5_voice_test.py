"""Voice testing page - embedded voice UI."""

import streamlit as st
from admin.components.auth import require_auth

st.set_page_config(
    page_title="Voice Test | Vartalaap",
    page_icon="V",
    layout="wide"
)


@require_auth
def main():
    st.title("Voice Bot Tester")
    st.caption("Test the voice bot with your microphone")

    # Instructions
    with st.expander("How to use", expanded=False):
        st.markdown("""
        1. Click **"Hold to Speak"** button
        2. Speak in **Hindi or English**
        3. Click again to stop recording
        4. Bot will respond with voice

        **Note:** Your browser will ask for microphone permission.
        """)

    # Embed the voice UI
    st.components.v1.iframe(
        src="https://localhost:8000/voice",
        height=700,
        scrolling=False
    )

    # Sidebar info
    with st.sidebar:
        st.subheader("Voice Test Info")
        st.info("""
        **Services:**
        - STT: Deepgram Nova-2
        - LLM: Groq Llama 3.3
        - TTS: ElevenLabs

        **Tip:** Speak clearly and wait for the bot to respond before speaking again.
        """)


if __name__ == "__main__":
    main()
