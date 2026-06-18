"""OmniSME AI Video Generator v3.0 — Streamlit entry point."""
import copy
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.home() / "ENV" / ".env")

import streamlit as st

from src.heygen_client import HeyGenClient
from src.script_generator import ScriptGenerator
from src.segment_selector import SegmentSelector
from src.video_merger import VideoMerger
from src.youtube_downloader import YouTubeDownloader
from src.youtube_processor import YouTubeProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Avatar / voice cache ──────────────────────────────────────────────────────

_AVATAR_CACHE = Path.home() / "ENV" / ".omnisme_avatar_cache.json"


def _load_avatar_cache():
    try:
        if _AVATAR_CACHE.exists():
            data = json.loads(_AVATAR_CACHE.read_text())
            return data.get("avatar_map", {}), data.get("voice_map", {})
    except Exception:
        pass
    return {}, {}


def _save_avatar_cache(avatar_map: dict, voice_map: dict) -> None:
    if not avatar_map:  # never persist an empty avatar list
        return
    try:
        _AVATAR_CACHE.write_text(
            json.dumps({"avatar_map": avatar_map, "voice_map": voice_map})
        )
    except Exception:
        pass

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="OmniSME AI Video Generator",
    page_icon="🎬",
    layout="wide",
)

# ── Session state defaults ────────────────────────────────────────────────────

_DEFAULTS = {
    "video_result": None,
    "liked_videos": [],
    "pipeline_inputs": {},
    "do_regenerate": False,
    "pending_render": {},
    "avatars_fetched": False,  # sentinel: True after first fetch attempt, even if empty
    "avatar_map": {},
    "voice_map": {},
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = copy.deepcopy(_v)  # each session gets its own mutable objects

# Pre-load from disk cache so avatars are available instantly (no API call on startup)
if not st.session_state.avatar_map and not st.session_state.voice_map:
    _cached_av, _cached_vo = _load_avatar_cache()
    if _cached_av:  # only treat as loaded when avatars are actually present
        st.session_state.avatar_map = _cached_av
        st.session_state.voice_map = _cached_vo
        st.session_state.avatars_fetched = True

# ── API keys ──────────────────────────────────────────────────────────────────

heygen_key = os.getenv("HEYGEN_API_KEY", "").strip()
openai_key = os.getenv("OPENAI_API_KEY", "").strip()

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("API Status")
    if heygen_key:
        st.success("HeyGen: Connected")
    else:
        st.error("HEYGEN_API_KEY missing")
    if openai_key:
        st.success("OpenAI: Connected")
    else:
        st.error("OPENAI_API_KEY missing")
    st.divider()

    liked = st.session_state.liked_videos
    if liked:
        st.subheader(f"👍 Liked Videos ({len(liked)})")
        for i, lv in enumerate(liked, 1):
            st.caption(f"{i}. {lv['topic']}")
        st.divider()

    st.caption("Output folder: ~/output/")

# ── Title ─────────────────────────────────────────────────────────────────────

st.title("🎬 OmniSME AI Video Generator")
st.markdown(
    "Generate a professional AI avatar video on any topic, sourced strictly "
    "from your YouTube URLs — with source footage playing in the background."
)
st.divider()

# ── Inputs (pre-filled on regenerate) ────────────────────────────────────────

pi = st.session_state.pipeline_inputs
col_topic, col_urls = st.columns([1, 1], gap="large")

with col_topic:
    topic = st.text_input(
        "Video Topic",
        value=pi.get("topic", ""),
        placeholder="e.g. Cisco QoS best practices for enterprise networks",
    )

with col_urls:
    youtube_urls_raw = st.text_area(
        "YouTube Source URLs (one per line)",
        value="\n".join(pi.get("urls", [])),
        placeholder="https://www.youtube.com/watch?v=...\nhttps://www.youtube.com/watch?v=...",
        height=130,
    )

# ── Advanced options ──────────────────────────────────────────────────────────

with st.expander("Advanced Options — Avatar, Voice & Layout"):
    avatar_map = st.session_state.avatar_map
    voice_map = st.session_state.voice_map

    # Show source of current data
    if avatar_map:
        st.caption(f"✅ {len(avatar_map)} avatar(s) loaded. Click Refresh to reload from HeyGen.")
    else:
        st.caption("⚠️ No avatars loaded yet. Click **Refresh from HeyGen** below.")

    # Refresh button — triggers a fresh API fetch and overwrites cache
    if heygen_key and st.button("🔄 Refresh from HeyGen", key="refresh_avatars"):
        _client_cfg = HeyGenClient(heygen_key)
        with st.spinner("Fetching avatars and voices from HeyGen…"):
            def _fetch_avatars():
                return {
                    a["avatar_name"]: a["avatar_id"]
                    for a in _client_cfg.list_avatars(limit=10)
                    if a.get("avatar_name")
                }

            def _fetch_voices():
                return {
                    v["name"]: v["voice_id"]
                    for v in _client_cfg.list_voices(limit=20)
                    if v.get("name")
                }

            with ThreadPoolExecutor(max_workers=2) as _pool:
                _fut_av = _pool.submit(_fetch_avatars)
                _fut_vo = _pool.submit(_fetch_voices)

                _new_av, _new_vo = {}, {}
                try:
                    _new_av = _fut_av.result()
                except Exception as _e:
                    st.warning(f"Avatar fetch failed: {_e}")

                try:
                    _new_vo = _fut_vo.result()
                except Exception as _e:
                    st.warning(f"Voice fetch failed: {_e}")

            if _new_av or _new_vo:
                st.session_state.avatar_map = _new_av
                st.session_state.voice_map = _new_vo
                st.session_state.avatars_fetched = True
                _save_avatar_cache(_new_av, _new_vo)
                st.success(f"Loaded {len(_new_av)} avatar(s) and {len(_new_vo)} voice(s). Cache saved.")
                st.rerun()

    # Auto-fetch on very first run (no cache file exists)
    if heygen_key and not st.session_state.avatars_fetched:
        _client_cfg = HeyGenClient(heygen_key)
        with st.spinner("First-time setup: loading avatars from HeyGen (saved for future sessions)…"):
            def _fetch_avatars_init():
                return {
                    a["avatar_name"]: a["avatar_id"]
                    for a in _client_cfg.list_avatars(limit=10)
                    if a.get("avatar_name")
                }

            def _fetch_voices_init():
                return {
                    v["name"]: v["voice_id"]
                    for v in _client_cfg.list_voices(limit=20)
                    if v.get("name")
                }

            with ThreadPoolExecutor(max_workers=2) as _pool:
                _fut_av = _pool.submit(_fetch_avatars_init)
                _fut_vo = _pool.submit(_fetch_voices_init)

                _init_av, _init_vo = {}, {}
                try:
                    _init_av = _fut_av.result()
                except Exception as _e:
                    st.warning(f"Avatar fetch failed: {_e}")

                try:
                    _init_vo = _fut_vo.result()
                except Exception as _e:
                    st.warning(f"Voice fetch failed: {_e}")

            st.session_state.avatar_map = _init_av
            st.session_state.voice_map = _init_vo
            if _init_av:
                st.session_state.avatars_fetched = True
                _save_avatar_cache(_init_av, _init_vo)
                st.rerun()
            # if avatar fetch failed, leave avatars_fetched=False so next rerun retries

    avatar_map = st.session_state.avatar_map
    voice_map = st.session_state.voice_map

    col_av, col_vo, col_layout = st.columns(3)
    with col_av:
        selected_avatar = st.selectbox(
            "Avatar",
            options=list(avatar_map) or ["(no avatars — click Refresh)"],
        )
    with col_vo:
        selected_voice = st.selectbox(
            "Voice",
            options=list(voice_map) or ["(no voices — click Refresh)"],
        )
    with col_layout:
        layout = st.selectbox(
            "Video Layout",
            options=[
                "Picture-in-Picture (YouTube bg + Avatar corner)",
                "Avatar Only",
            ],
            help=(
                "PiP: YouTube source clips play full-screen (muted); "
                "avatar narrates in the bottom-right corner.\n"
                "Avatar Only: HeyGen avatar on a plain background."
            ),
        )

    # Manual override — lets user paste IDs directly if dropdown is empty
    with st.expander("Manual Avatar / Voice ID override"):
        st.caption("Paste IDs directly from your HeyGen dashboard if the dropdown above is empty.")
        manual_avatar_id = st.text_input("Avatar ID (optional)", placeholder="e.g. Monica_inSuit_20220818")
        manual_voice_id = st.text_input("Voice ID (optional)", placeholder="e.g. 1bd001a7e50043a58eaa ea35e1b8101b0")

# ── Top action row ────────────────────────────────────────────────────────────

col_gen, col_new_top = st.columns([3, 1])
with col_gen:
    api_ready = bool(heygen_key and openai_key)
    inputs_ready = bool(topic.strip() and youtube_urls_raw.strip())
    generate_clicked = st.button(
        "▶ Generate Video",
        type="primary",
        disabled=not (api_ready and inputs_ready),
        use_container_width=True,
    )
with col_new_top:
    if st.button("＋ New Topic", use_container_width=True, help="Clear everything and start fresh"):
        for k, v in _DEFAULTS.items():
            st.session_state[k] = copy.deepcopy(v)
        st.rerun()

# ── Pipeline helpers ──────────────────────────────────────────────────────────

def _download_and_merge(
    client: HeyGenClient,
    avatar_url: str,
    topic: str,
    use_pip: bool,
    urls: list,
    relevant_segments: list,
    pb,
    sb,
) -> str:
    """Download the rendered avatar video, optionally merge with topic-relevant YouTube clips."""
    sb.info("Downloading avatar video from HeyGen…")
    pb.progress(78, text="Downloading avatar video…")
    avatar_path = client.download_video(avatar_url, topic + "_avatar")

    if use_pip:
        pb.progress(86, text="Downloading relevant YouTube segments…")
        downloader = YouTubeDownloader()
        try:
            def _clip_status(msg: str):
                sb.info(msg)

            if relevant_segments:
                youtube_clips = downloader.download_segments(
                    relevant_segments, status_callback=_clip_status
                )
                clip_source = "relevant segments"
            else:
                # Fallback: download first portion of each URL
                youtube_clips = downloader.download_clips(urls, status_callback=_clip_status)
                clip_source = "first portion of each video"

            if youtube_clips:
                sb.info(
                    f"Downloaded {len(youtube_clips)} clip(s) ({clip_source}). "
                    "Merging with avatar (PiP)…"
                )
                pb.progress(93, text="Merging videos…")
                try:
                    final_path = VideoMerger().merge(avatar_path, youtube_clips, topic)
                except Exception as merge_exc:
                    st.warning(
                        f"PiP merge failed ({merge_exc}); falling back to Avatar Only layout."
                    )
                    logger.exception("VideoMerger error")
                    final_path = avatar_path
            else:
                st.warning(
                    "No YouTube clips could be downloaded "
                    "(videos may be age-restricted, private, or unavailable). "
                    "Falling back to Avatar Only layout."
                )
                final_path = avatar_path
        finally:
            downloader.cleanup()
    else:
        final_path = avatar_path

    pb.progress(100, text="Done!")
    sb.success(f"Video saved: {final_path}")
    return str(final_path)


def run_pipeline(topic: str, urls: list, avatar_id: str, voice_id: str, use_pip: bool):
    pb = st.progress(0, text="Starting pipeline…")
    sb = st.empty()

    try:
        # Stage 1 — Transcripts
        sb.info(f"Extracting transcripts from {len(urls)} URL(s)…")
        pb.progress(8, text="Extracting YouTube transcripts…")
        docs = YouTubeProcessor().load(urls)
        if not docs:
            st.error("No transcripts found. Ensure the YouTube videos have captions.")
            pb.empty()
            return None

        # Stage 2 — Script
        sb.info(f"{len(docs)} transcript(s) loaded. Generating script with GPT-4o…")
        pb.progress(22, text="Building presenter script…")
        script = ScriptGenerator().build(docs, topic)
        with st.expander("View generated script"):
            st.text_area("Script", script, height=260, label_visibility="collapsed")

        # Stage 2.5 — Find topic-relevant video segments (PiP only)
        relevant_segments = []
        if use_pip:
            sb.info("Identifying topic-relevant video segments…")
            pb.progress(38, text="Selecting relevant video segments…")
            try:
                relevant_segments = SegmentSelector().get_relevant_segments(
                    urls, topic, script
                )
                if relevant_segments:
                    sb.info(
                        f"Found {len(relevant_segments)} relevant segment(s) from source videos."
                    )
                else:
                    sb.info("No high-relevance segments found; will use start of each video.")
            except Exception as seg_exc:
                logger.warning("Segment selection failed: %s — using fallback", seg_exc)

        # Stage 3 — HeyGen: create video
        sb.info("Submitting script to HeyGen for avatar video generation…")
        pb.progress(50, text="Submitting to HeyGen…")
        client = HeyGenClient(heygen_key)
        video_id = client.create_video(script, avatar_id, voice_id)

        # Save immediately so a timeout can be resumed without restarting
        st.session_state.pending_render = {
            "video_id": video_id,
            "topic": topic,
            "urls": urls,
            "avatar_id": avatar_id,
            "voice_id": voice_id,
            "use_pip": use_pip,
            "relevant_segments": relevant_segments,
        }

        # Stage 4 — HeyGen: poll until rendered
        sb.info(f"HeyGen rendering avatar video (ID: {video_id})…")

        def _on_poll(frac: float, elapsed_s: int):
            mins, secs = divmod(elapsed_s, 60)
            pct = 52 + int(frac * 24)
            pb.progress(pct, text=f"Avatar rendering… {mins}m {secs:02d}s elapsed")

        try:
            avatar_url = client.poll_status(video_id, timeout=1800, progress_callback=_on_poll)
        except TimeoutError as te:
            pb.empty()
            sb.warning(
                f"HeyGen is still rendering (30-min limit reached). "
                f"The video ID **{video_id}** has been saved — click **Check Status** below to resume."
            )
            return None  # pending_render stays set; resume section will appear

        # Stage 5 & 6 — Download + optional PiP merge
        st.session_state.pending_render = {}  # render complete, clear pending state
        return _download_and_merge(
            client, avatar_url, topic, use_pip, urls, relevant_segments, pb, sb
        )

    except Exception as exc:
        sb.error(f"Pipeline failed: {exc}")
        pb.empty()
        logging.exception("Pipeline error")
        return None


def resume_pipeline():
    """Re-poll HeyGen for an already-submitted render, then download and merge."""
    pr = st.session_state.pending_render
    video_id = pr["video_id"]
    topic = pr["topic"]
    urls = pr["urls"]
    use_pip = pr["use_pip"]
    relevant_segments = pr.get("relevant_segments", [])
    client = HeyGenClient(heygen_key)

    pb = st.progress(52, text="Resuming — checking HeyGen render status…")
    sb = st.empty()
    sb.info(f"Polling HeyGen for video ID {video_id}…")

    def _on_poll(frac: float, elapsed_s: int):
        mins, secs = divmod(elapsed_s, 60)
        pct = 52 + int(frac * 24)
        pb.progress(pct, text=f"Avatar rendering… {mins}m {secs:02d}s elapsed")

    try:
        avatar_url = client.poll_status(video_id, timeout=1800, progress_callback=_on_poll)
    except TimeoutError:
        pb.empty()
        sb.warning(
            "Still rendering. Wait a few more minutes and click **Check Status** again."
        )
        return None

    except Exception as exc:
        pb.empty()
        sb.error(f"Resume failed: {exc}")
        logging.exception("Resume error")
        return None

    st.session_state.pending_render = {}
    return _download_and_merge(
        client, avatar_url, topic, use_pip, urls, relevant_segments, pb, sb
    )


# ── Trigger ───────────────────────────────────────────────────────────────────

trigger = generate_clicked or st.session_state.do_regenerate

if trigger and topic.strip() and youtube_urls_raw.strip():
    st.session_state.do_regenerate = False
    urls = [u.strip() for u in youtube_urls_raw.splitlines() if u.strip()]
    # Manual override takes precedence over dropdown selection
    avatar_id = manual_avatar_id.strip() or avatar_map.get(selected_avatar)
    voice_id = manual_voice_id.strip() or voice_map.get(selected_voice)

    if not avatar_id or not voice_id:
        st.error("No valid avatar or voice selected. Verify your HeyGen API key.")
    else:
        st.session_state.pipeline_inputs = {"topic": topic, "urls": urls}
        use_pip = "Picture-in-Picture" in layout
        result_path = run_pipeline(topic, urls, avatar_id, voice_id, use_pip)
        if result_path:
            st.session_state.video_result = {
                "path": result_path,
                "topic": topic,
                "urls": urls,
                "liked": False,
            }

# ── Resume panel (shown when a render timed out but video_id is known) ────────

if st.session_state.pending_render.get("video_id"):
    pr = st.session_state.pending_render
    st.divider()
    st.warning(
        f"⏳ HeyGen render in progress — Video ID: `{pr['video_id']}`  \n"
        "The render is still running on HeyGen's servers. Click **Check Status** to resume."
    )
    col_resume, col_cancel = st.columns([2, 1])
    with col_resume:
        if st.button("🔄 Check Status", type="primary", key="resume_btn", use_container_width=True):
            result_path = resume_pipeline()
            if result_path:
                st.session_state.video_result = {
                    "path": result_path,
                    "topic": pr["topic"],
                    "urls": pr["urls"],
                    "liked": False,
                }
                st.rerun()
    with col_cancel:
        if st.button("✕ Cancel Render", key="cancel_btn", use_container_width=True):
            st.session_state.pending_render = {}
            st.rerun()

# ── Results panel ─────────────────────────────────────────────────────────────

if st.session_state.video_result:
    result = st.session_state.video_result
    vpath = Path(result["path"])

    st.divider()
    st.subheader(f"Generated Video — {result['topic']}")

    if vpath.exists():
        st.video(str(vpath))
        with open(vpath, "rb") as fh:
            st.download_button(
                "⬇ Download MP4",
                data=fh,
                file_name=vpath.name,
                mime="video/mp4",
            )
    else:
        st.warning(f"Video file not found on disk: {vpath}")

    st.write("")
    col_like, col_regen, col_new2 = st.columns(3)

    with col_like:
        if result.get("liked"):
            st.success("👍 Liked!")
        elif st.button("👍 Like this video", key="like_btn"):
            st.session_state.video_result["liked"] = True
            if result not in st.session_state.liked_videos:
                st.session_state.liked_videos.append(dict(result))
            st.rerun()

    with col_regen:
        if st.button(
            "🔄 Regenerate",
            key="regen_btn",
            help="Re-run the full pipeline with the same topic and URLs",
        ):
            st.session_state.do_regenerate = True
            st.session_state.video_result = None
            st.rerun()

    with col_new2:
        if st.button(
            "＋ New Topic",
            key="new_btn2",
            help="Clear inputs and generate a video on a completely new topic",
        ):
            for k, v in _DEFAULTS.items():
                st.session_state[k] = copy.deepcopy(v)
            st.rerun()
