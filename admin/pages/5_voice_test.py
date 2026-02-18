"""Voice testing page - embedded voice UI."""

import html
import os

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
    voice_test_url = os.environ.get("VOICE_TEST_URL", "http://localhost:8000/voice")
    escaped_voice_url = html.escape(voice_test_url, quote=True)

    # Instructions
    with st.expander("How to use", expanded=False):
        st.markdown("""
        1. Click **"Start Call"** button
        2. Speak in **Hindi or English**
        3. Wait for the bot to respond
        4. Click **"End Call"** when done

        **Note:** Your browser will ask for microphone permission.
        """)

    # Embed the voice UI with explicit mic permission delegation.
    # Streamlit's iframe helper does not expose an `allow` attribute.
    st.components.v1.html(
        f"""
        <div style="display:flex;flex-direction:column;gap:8px;">
          <iframe
            src="{escaped_voice_url}"
            title="Voice Bot Interface"
            style="width:100%;height:700px;border:0;border-radius:12px;"
            allow="microphone; autoplay"
          ></iframe>
          <div style="font-size:12px;color:#6b7280;">
            If mic is still blocked in embedded mode, open standalone:
            <a href="{escaped_voice_url}" target="_blank" rel="noopener noreferrer">{escaped_voice_url}</a>
          </div>
        </div>
        """,
        height=740,
        scrolling=False,
    )

    # Sidebar info
    with st.sidebar:
        st.subheader("Voice Test Info")
        st.info("""
        **Services:**
        - STT: Deepgram Nova-2
        - LLM: Groq Llama 3.3
        - TTS: Cartesia Sonic

        **Tip:** Speak clearly and wait for the bot to respond before speaking again.
        """)
        st.caption(f"Voice UI URL: {voice_test_url}")


if __name__ == "__main__":
    main()
