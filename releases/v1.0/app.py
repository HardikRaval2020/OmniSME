"""OmniSME AI Video Generator — Streamlit entry point."""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Load API keys from ~/ENV/.env before any other imports that read env vars
load_dotenv(Path.home() / "ENV" / ".env")

import streamlit as st

from src.heygen_client import HeyGenClient
from src.script_generator import ScriptGenerator
from src.youtube_processor import YouTubeProcessor

logging.basicConfig(level=logging.INFO)

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="OmniSME AI Video Generator",
    page_icon="🎬",
    layout="wide",
)

# ── Sidebar — API status ──────────────────────────────────────────────────────

with st.sidebar:
    st.header("API Status")
    heygen_key = os.getenv("HEYGEN_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    if heygen_key:
        st.success("HeyGen API key loaded")
    else:
        st.error("HEYGEN_API_KEY missing in ~/ENV/.env")

    if openai_key:
        st.success("OpenAI API key loaded")
    else:
        st.error("OPENAI_API_KEY missing in ~/ENV/.env")

    st.divider()
    st.caption("Output folder: ~/output/")

# ── Title ─────────────────────────────────────────────────────────────────────

st.title("OmniSME AI Video Generator")
st.markdown(
    "Generate a professional AI avatar video on any topic, "
    "sourced strictly from the YouTube videos you provide."
)
st.divider()

# ── Inputs ───────────────────────────────────────────────────────────────────

col_topic, col_urls = st.columns([1, 1], gap="large")

with col_topic:
    topic = st.text_input(
        "Video Topic",
        placeholder="e.g. Cisco QoS best practices for enterprise networks",
        help="The specific topic the AI presenter should cover.",
    )

with col_urls:
    youtube_urls_raw = st.text_area(
        "YouTube Source URLs (one per line)",
        placeholder=(
            "https://www.youtube.com/watch?v=...\n"
            "https://www.youtube.com/watch?v=..."
        ),
        height=130,
        help="Videos must have captions or auto-generated transcripts.",
    )

# ── Advanced options ─────────────────────────────────────────────────────────

with st.expander("Advanced Options — Avatar & Voice"):
    avatar_map: dict = {}
    voice_map: dict = {}

    if heygen_key:
        client_cfg = HeyGenClient(heygen_key)
        try:
            avatars = client_cfg.list_avatars()
            avatar_map = {a["avatar_name"]: a["avatar_id"] for a in avatars if a.get("avatar_name")}
        except Exception as exc:
            st.warning(f"Could not fetch avatars: {exc}")

        try:
            voices = client_cfg.list_voices()
            voice_map = {v["name"]: v["voice_id"] for v in voices if v.get("name")}
        except Exception as exc:
            st.warning(f"Could not fetch voices: {exc}")

    col_av, col_vo = st.columns(2)
    with col_av:
        selected_avatar = st.selectbox(
            "Avatar",
            options=list(avatar_map.keys()) if avatar_map else ["(load failed — check key)"],
        )
    with col_vo:
        selected_voice = st.selectbox(
            "Voice",
            options=list(voice_map.keys()) if voice_map else ["(load failed — check key)"],
        )

# ── Generate button ───────────────────────────────────────────────────────────

ready = bool(topic.strip() and youtube_urls_raw.strip() and heygen_key and openai_key)
if st.button("Generate Video", type="primary", disabled=not ready):
    urls = [u.strip() for u in youtube_urls_raw.splitlines() if u.strip()]

    avatar_id = avatar_map.get(selected_avatar)
    voice_id = voice_map.get(selected_voice)

    if not avatar_id or not voice_id:
        st.error("No valid avatar or voice selected. Verify your HeyGen API key.")
        st.stop()

    progress_bar = st.progress(0, text="Starting pipeline…")
    status_box = st.empty()

    try:
        # ── Stage 1: YouTube transcripts ─────────────────────────────────────
        status_box.info(f"Extracting transcripts from {len(urls)} YouTube URL(s)…")
        progress_bar.progress(10, text="Extracting YouTube transcripts…")

        processor = YouTubeProcessor()
        docs = processor.load(urls)

        if not docs:
            st.error(
                "No transcripts found. "
                "Make sure the YouTube videos have captions or auto-generated subtitles."
            )
            progress_bar.empty()
            st.stop()

        status_box.info(f"Loaded {len(docs)} transcript document(s). Building script…")
        progress_bar.progress(30, text="Transcripts loaded — generating script with GPT-4o…")

        # ── Stage 2: Script generation ────────────────────────────────────────
        generator = ScriptGenerator()
        script = generator.build(docs, topic)

        with st.expander("View generated script"):
            st.text_area("Script", script, height=300, label_visibility="collapsed")

        status_box.info("Script ready. Submitting to HeyGen…")
        progress_bar.progress(55, text="Script ready — submitting to HeyGen…")

        # ── Stage 3: HeyGen video creation ────────────────────────────────────
        client = HeyGenClient(heygen_key)
        video_id = client.create_video(script, avatar_id, voice_id)

        status_box.info(f"HeyGen rendering video (ID: {video_id}). This may take several minutes…")
        progress_bar.progress(65, text="Rendering avatar video…")

        # ── Stage 4: Poll until complete ──────────────────────────────────────
        def _on_poll(fraction: float):
            pct = 65 + int(fraction * 25)
            progress_bar.progress(pct, text=f"Rendering… {pct}%")

        video_url = client.poll_status(video_id, timeout=600, progress_callback=_on_poll)

        status_box.info("Downloading MP4 to ~/output/…")
        progress_bar.progress(92, text="Downloading…")

        # ── Stage 5: Download ─────────────────────────────────────────────────
        local_path = client.download_video(video_url, topic)
        progress_bar.progress(100, text="Done!")

        # ── Results ───────────────────────────────────────────────────────────
        status_box.success(f"Video saved: {local_path}")
        st.video(str(local_path))

        with open(local_path, "rb") as fh:
            st.download_button(
                label="Download MP4",
                data=fh,
                file_name=local_path.name,
                mime="video/mp4",
            )

    except Exception as exc:
        status_box.error(f"Pipeline failed: {exc}")
        progress_bar.empty()
        logging.exception("Pipeline error")

elif not ready and st.session_state.get("_generate_clicked"):
    st.warning("Fill in the topic, at least one YouTube URL, and ensure both API keys are set.")
