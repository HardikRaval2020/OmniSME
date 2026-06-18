# OmniSME — AI Video Generator

> **Scaling Knowledge Delivery through Generative AI**
> Turn any YouTube knowledge base into a polished, AI-avatar-narrated expert video — in ~25 minutes, not days.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35%2B-FF4B4B?logo=streamlit)](https://streamlit.io)
[![LangChain](https://img.shields.io/badge/LangChain-0.2%2B-green)](https://python.langchain.com)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?logo=openai)](https://openai.com)
[![HeyGen](https://img.shields.io/badge/HeyGen-API%20v2-blueviolet)](https://heygen.com)
[![Version](https://img.shields.io/badge/version-v3.0-brightgreen)](#version-history)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](#license)

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [5-Stage AI Pipeline](#5-stage-ai-pipeline)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the App](#running-the-app)
- [How to Use](#how-to-use)
- [Module Reference](#module-reference)
- [Version History](#version-history)
- [Release Management & Rollback](#release-management--rollback)
- [Authors](#authors)
- [License](#license)

---

## Overview

**OmniSME** is a Streamlit-based AI application that automates the end-to-end creation of expert-level knowledge videos for Cisco Customer Experience (CX) teams. Given one or more YouTube source URLs and a topic, it:

1. Extracts transcripts using LangChain's `YoutubeLoader`
2. Retrieves the most relevant content via FAISS vector search
3. Generates a structured presenter script with GPT-4o
4. Selects the most topic-relevant video segments for background footage
5. Renders a professional AI avatar via HeyGen API v2
6. Composites a **Picture-in-Picture** (PiP) final MP4 — avatar in the corner, source footage full-screen

**Before OmniSME:** 40+ hours · $15,000 production cost · 3–6 week delivery cycle
**After OmniSME:** ~25 minutes · ~$4.50 API cost · zero video editing expertise required

### Who is it for?

| Role | Use Case |
|------|----------|
| Customer Success Managers | On-demand product introductions for new customers |
| Solutions Engineers | Technical topic deep-dives without scheduling SMEs |
| Training & Enablement | Scalable onboarding content at a fraction of the cost |
| Hackathon / Innovation Teams | Rapid prototyping of knowledge automation |

---

## Key Features

### Core Capabilities

- **Full RAG Pipeline** — FAISS + `text-embedding-3-small` retrieves the most relevant transcript chunks before GPT-4o writes the script, ensuring accuracy and no hallucinations
- **Picture-in-Picture Layout** — HeyGen avatar plays in the bottom-right corner; topic-relevant YouTube source footage plays full-screen behind it (muted)
- **Smart Segment Selection** *(v3.0)* — Keyword-based timestamp scoring selects the most topically relevant 20-second windows from source videos as background, not just the first 2 minutes
- **Multi-Avatar & Voice** — Browse your full HeyGen avatar and voice library directly in the UI
- **Resilient Render Resumption** — HeyGen renders can take 30+ minutes; OmniSME saves the `video_id` to session state so you can resume polling in any later session without restarting
- **Like / Regenerate / New Topic** — Post-generation actions let you iterate quickly without re-entering inputs
- **Versioned Releases** — Rollback to any prior version (`releases/v1.0/`, `releases/v2.0/`) at any time

### Layout Options

| Mode | Description |
|------|-------------|
| **Picture-in-Picture** | Topic-relevant YouTube clips (muted, full-screen) + avatar in bottom-right corner |
| **Avatar Only** | HeyGen avatar on a plain dark background — automatic fallback if YouTube download fails |

---

## 5-Stage AI Pipeline

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │                   OmniSME AI Pipeline (v3.0)                        │
  └─────────────────────────────────────────────────────────────────────┘

  📥 STAGE 1          🧠 STAGE 2          🔍 STAGE 3
  Transcript    ───►  RAG Script    ───►  Segment
  Extraction          Generation          Selection
  ──────────          ──────────          ─────────
  LangChain           FAISS +             Keyword-scored
  YoutubeLoader       GPT-4o              20-second windows
  pulls captions      writes structured   from transcripts;
  from all source     presenter script    selects top-N
  URLs into a         (hook, body, CTA)   timestamp ranges
  document corpus     max 1,500 words     for PiP footage

  🤖 STAGE 4          🎬 STAGE 5
  HeyGen Avatar ───►  PiP Merge
  Rendering           & Export
  ─────────────       ──────────
  HeyGen REST         yt-dlp downloads
  API v2; chosen      relevant segments;
  avatar + voice      MoviePy composites
  render narration    avatar over footage;
  video (adaptive     output MP4 saved to
  polling, 1800s      ~/output/
  timeout)

  ──────────────────────────────────────────────────────────────────────
  Total pipeline time: ~25 minutes end-to-end (dominated by HeyGen render)
  Cost per video:      ~$4.50 (OpenAI API + HeyGen API calls)
  ──────────────────────────────────────────────────────────────────────
```

### Fallback Chain

Every stage degrades gracefully:

```
Transcript unavailable  →  skip that URL silently
No keyword overlap      →  fall back to first 2 min of each video
Segment range download fails  →  full download (MoviePy trims)
All clips fail          →  Avatar Only layout
PiP merge fails         →  Avatar Only layout (warning shown)
HeyGen times out        →  save video_id; user clicks "Check Status" to resume
```

---

## Tech Stack

| Layer | Library / API | Role |
|-------|--------------|------|
| **UI** | [Streamlit](https://streamlit.io) ≥ 1.35 | Browser-based front-end, session state, progress bars |
| **Transcript Loading** | [LangChain Community](https://python.langchain.com) — `YoutubeLoader` | Pull captions from YouTube URLs into `Document` objects |
| **Transcript Timestamps** | [youtube-transcript-api](https://pypi.org/project/youtube-transcript-api/) | Fetch `{text, start, duration}` segments for PiP selection |
| **Vector Store** | [FAISS](https://github.com/facebookresearch/faiss) (`faiss-cpu`) | Similarity search over transcript chunks |
| **Embeddings** | OpenAI `text-embedding-3-small` | Encode chunks for FAISS indexing |
| **Script Generation** | OpenAI `gpt-4o` (max\_tokens=3000) | Write structured 1,500-word presenter script |
| **Avatar Rendering** | [HeyGen REST API v2](https://docs.heygen.com) | Render avatar video from script (async, polled) |
| **Video Download** | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Download YouTube clips with range support and DASH fallback |
| **Video Compositing** | [MoviePy](https://zulko.github.io/moviepy/) 1.x | PiP layout — avatar overlay on full-screen background |
| **HTTP** | [Requests](https://requests.readthedocs.io) | HeyGen API calls with retry and timeout |
| **Config** | [python-dotenv](https://pypi.org/project/python-dotenv/) | Load API keys from `~/ENV/.env` |

---

## Project Structure

```
OmniSME_2/
│
├── app.py                          # Streamlit entry point — full pipeline orchestration
├── requirements.txt                # Python dependencies
├── VERSION                         # Current version (v3.0)
│
├── src/
│   ├── __init__.py
│   ├── youtube_processor.py        # Stage 1: LangChain YoutubeLoader wrapper
│   ├── script_generator.py         # Stage 2: FAISS RAG + GPT-4o script writer
│   ├── segment_selector.py         # Stage 3: Timestamp scoring for PiP (v3.0)
│   ├── heygen_client.py            # Stage 4: HeyGen API v2 client
│   ├── youtube_downloader.py       # Stage 5a: yt-dlp clip + segment downloader
│   └── video_merger.py             # Stage 5b: MoviePy PiP compositor
│
└── releases/
    ├── v1.0/                       # Avatar-only version (no PiP)
    │   ├── app.py
    │   ├── requirements.txt
    │   └── src/
    └── v2.0/                       # PiP version (first 2 min, not topic-selected)
        ├── app.py
        ├── requirements.txt
        └── src/
```

### Key Files Explained

| File | Responsibility |
|------|---------------|
| `app.py` | Session state init, sidebar, avatar/voice cache, `run_pipeline()`, `resume_pipeline()`, `_download_and_merge()`, action buttons |
| `src/youtube_processor.py` | Wraps `YoutubeLoader`; silently skips URLs without captions |
| `src/script_generator.py` | Splits docs → FAISS index → retrieves top-15 chunks → GPT-4o → script string |
| `src/segment_selector.py` | Fetches timestamped transcripts; scores 20-second windows by keyword overlap; returns `(url, start, end)` tuples |
| `src/heygen_client.py` | `create_video()`, `poll_status()` (adaptive 15s/30s interval, 1800s timeout), `download_video()`, `_split_script()` |
| `src/youtube_downloader.py` | `download_clips()` (first 2 min fallback), `download_segments()` (targeted timestamps), DASH-aware two-stage download |
| `src/video_merger.py` | `merge()` builds PiP with MoviePy; `_build_background()` stitches + loops clips to match avatar duration |

---

## Prerequisites

| Requirement | Notes |
|------------|-------|
| Python 3.10+ | Tested on 3.11 and 3.12 |
| [ffmpeg](https://ffmpeg.org/download.html) | Required by MoviePy and yt-dlp for video processing |
| OpenAI API key | Needs access to `gpt-4o` and `text-embedding-3-small` |
| HeyGen API key | [Sign up](https://heygen.com) — avatar library and voice roster required |
| Internet access | For YouTube transcript fetching and HeyGen rendering |

### Install ffmpeg (macOS)

```bash
brew install ffmpeg
```

### Install ffmpeg (Ubuntu/Debian)

```bash
sudo apt update && sudo apt install ffmpeg -y
```

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/<your-org>/OmniSME.git
cd OmniSME

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Configuration

OmniSME reads API keys **exclusively** from `~/ENV/.env`. Do **not** create this file or directory — it is expected to already exist on your machine.

### `~/ENV/.env` format

```dotenv
OPENAI_API_KEY=sk-...
HEYGEN_API_KEY=...
```

### Output directory

Generated MP4 files are written to `~/output/`. This directory must already exist:

```bash
mkdir -p ~/output
```

> **Security note:** The app never creates, overwrites, or reads from `~/ENV/.env` beyond `load_dotenv()`. API keys are never written to disk by the app.

---

## Running the App

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501` in your default browser.

---

## How to Use

### Step 1 — Enter a Topic

Type a specific technical topic in the **Video Topic** field.

```
Example: Cisco QoS best practices for enterprise networks
```

### Step 2 — Add YouTube Source URLs

Paste one YouTube URL per line. These videos must have English captions.

```
https://www.youtube.com/watch?v=example1
https://www.youtube.com/watch?v=example2
```

### Step 3 — Configure Avatar & Layout (optional)

Expand **Advanced Options** to select:
- **Avatar** — any avatar from your HeyGen account
- **Voice** — any English voice from your HeyGen account
- **Layout** — `Picture-in-Picture` (recommended) or `Avatar Only`

### Step 4 — Generate

Click **▶ Generate Video**. The progress bar tracks all 5 pipeline stages:

```
0%   → Extracting YouTube transcripts
22%  → Building presenter script (GPT-4o)
38%  → Selecting relevant video segments
50%  → Submitting to HeyGen
52-76% → Avatar rendering (adaptive polling)
78%  → Downloading avatar video
86%  → Downloading relevant YouTube segments
93%  → Merging videos (PiP)
100% → Done — video saved to ~/output/
```

### Step 5 — Review & Act

Once complete, the video plays inline. Three actions are available:

| Button | Action |
|--------|--------|
| 👍 **Like this video** | Saves to the Liked Videos sidebar |
| 🔄 **Regenerate** | Re-runs the full pipeline with the same inputs |
| ＋ **New Topic** | Clears everything and starts fresh |

### HeyGen Render Timeout

If HeyGen takes longer than 30 minutes (the render is still running on HeyGen's servers), OmniSME saves the `video_id` and shows a **Check Status** button. Click it to resume polling without restarting the pipeline.

---

## Module Reference

### `YouTubeProcessor` (`src/youtube_processor.py`)

```python
from src.youtube_processor import YouTubeProcessor

docs = YouTubeProcessor().load([
    "https://www.youtube.com/watch?v=..."
])
# Returns: List[langchain_core.documents.Document]
```

### `ScriptGenerator` (`src/script_generator.py`)

```python
from src.script_generator import ScriptGenerator

script = ScriptGenerator().build(docs, topic="Cisco QoS")
# Returns: str — structured presenter script (≤1,500 words)
```

Internally: `split_documents` → FAISS index → retrieve top-15 chunks → GPT-4o with structured prompt (hook, intro, 3 key points, examples, CTA).

### `SegmentSelector` (`src/segment_selector.py`) *(v3.0)*

```python
from src.segment_selector import SegmentSelector

segments = SegmentSelector().get_relevant_segments(
    urls=["https://www.youtube.com/watch?v=..."],
    topic="Cisco QoS",
    script=script,        # optional — improves keyword coverage
    max_segments=6,       # max number of clips to return
    window_secs=20,       # scoring window size in seconds
)
# Returns: List[Tuple[str, float, float]]
#   → [(url, start_sec, end_sec), ...]
```

**Scoring algorithm:**
1. Extract meaningful keywords from `topic + script` (stop-word filtered, ≥4 chars)
2. For each URL, fetch `{text, start, duration}` segments via `YouTubeTranscriptApi`
3. Slide a 20-second window and score each window by keyword-set intersection
4. Sort candidates by score, de-duplicate overlapping windows per URL
5. Return top-N `(url, start, end)` tuples

### `HeyGenClient` (`src/heygen_client.py`)

```python
from src.heygen_client import HeyGenClient

client = HeyGenClient(api_key="...")

# List avatars/voices
avatars = client.list_avatars()   # List[Dict]
voices  = client.list_voices()    # List[Dict] — English only

# Create and poll
video_id  = client.create_video(script, avatar_id, voice_id)
video_url = client.poll_status(video_id, timeout=1800)   # raises TimeoutError

# Download
path = client.download_video(video_url, topic="My Topic")
```

**Key behaviours:**
- `_get_with_retry()` — 30s timeout, 2 retries with 5s backoff
- `poll_status()` — 15s interval for first 2 min, 30s thereafter; fires `progress_callback(frac, elapsed_s)`
- `_split_script()` — splits script into ≤1,400-char chunks per HeyGen slide limit; strips trailing double-periods

### `YouTubeDownloader` (`src/youtube_downloader.py`)

```python
from src.youtube_downloader import YouTubeDownloader

dl = YouTubeDownloader()
try:
    # Topic-relevant targeted segments (v3.0 primary path)
    clips = dl.download_segments(segments, status_callback=print)

    # Or: first 2-min fallback
    clips = dl.download_clips(urls, status_callback=print)
finally:
    dl.cleanup()   # removes all temp dirs
```

**Download strategy per segment:**
1. Range-capped download with `download_range_func(None, [(start, end)])`
2. If range fails (DASH stream) → full download; MoviePy trims in `_build_background()`

### `VideoMerger` (`src/video_merger.py`)

```python
from src.video_merger import VideoMerger

output_path = VideoMerger().merge(
    avatar_path=Path("..."),
    youtube_clips=[Path("..."), ...],
    topic="Cisco QoS"
)
# Returns: Path to ~/output/<topic>_<timestamp>.mp4
```

**PiP layout:** 1280×720 output; avatar scaled to 28% of width, positioned bottom-right with 20px margin; YouTube clips full-screen background (muted); avatar audio preserved.

---

## Version History

### v3.0 (Current) — Topic-Relevant PiP Background

> Archive: `releases/v2.0/`

**What changed:**
- Added `src/segment_selector.py` — keyword-based timestamp scoring selects the most topically relevant 20-second windows from source videos
- Updated `src/youtube_downloader.py` — new `download_segments()` / `_download_segment()` methods for targeted time-range downloads
- Updated `app.py` — pipeline stage 2.5 selects relevant segments after script generation; `relevant_segments` stored in `pending_render` for timeout resume

### v2.0 — Picture-in-Picture + Action Buttons

> Archive: `releases/v1.0/`

**What changed:**
- Added yt-dlp YouTube video download (first 2 min of each URL)
- Added MoviePy PiP compositor (`src/video_merger.py`)
- Added 👍 Like, 🔄 Regenerate, ＋ New Topic action buttons
- Fixed HeyGen 600s timeout → 1800s with adaptive polling and resume
- Fixed repeated avatar fetch timeouts → session state cache with boolean sentinel
- Fixed `PIL.Image.ANTIALIAS` error for Pillow 10+ compatibility
- Fixed 9 bugs: mutable session state aliasing, double-close in merger, FAISS empty-chunks crash, `max_tokens` truncation, avatar cache race, `data["video_url"]` KeyError, double-period in `_split_script`, frame-corruption in background loop

### v1.0 — Avatar-Only Baseline

**What was included:**
- Streamlit UI with topic + YouTube URL inputs
- LangChain YoutubeLoader → FAISS → GPT-4o script
- HeyGen avatar video generation
- MP4 output to `~/output/`

---

## Release Management & Rollback

Every release is archived in `releases/` before changes are applied. To roll back:

```bash
# Roll back to v2.0
cp releases/v2.0/app.py app.py
cp releases/v2.0/requirements.txt requirements.txt
cp releases/v2.0/src/* src/
echo "v2.0" > VERSION

# Roll back to v1.0
cp releases/v1.0/app.py app.py
cp releases/v1.0/requirements.txt requirements.txt
cp releases/v1.0/src/* src/
echo "v1.0" > VERSION
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | ✅ | OpenAI API key — used for `gpt-4o` and `text-embedding-3-small` |
| `HEYGEN_API_KEY` | ✅ | HeyGen API key — used for avatar listing, video creation, polling |

Both are loaded via `python-dotenv` from `~/ENV/.env`. The app raises no errors at startup if keys are missing — instead the sidebar shows a red status indicator and the **Generate** button is disabled.

---

## Common Issues

### "No transcripts found"

YouTube videos must have English captions. Check:
- Video has CC/captions enabled
- Video is not age-restricted or private
- Language setting: the app tries `en`, `en-US`, `en-GB` in order

### "HeyGen render timed out"

HeyGen renders are queued server-side. The 30-minute timeout is a client-side safeguard only — the render is still running. Click **Check Status** to resume polling; the video ID is saved in session state.

### "PiP merge failed"

Usually a MoviePy/ffmpeg version conflict. The app automatically falls back to Avatar Only layout and shows a warning. Check ffmpeg is on PATH:

```bash
ffmpeg -version
```

### "Could not fetch avatars / voices"

HeyGen's avatar API can be slow at peak times. OmniSME retries twice with 5-second backoff. If it still fails, the avatar dropdown shows `(check HeyGen key)` — refresh the page to retry.

---

## Authors

| Name | Role |
|------|------|
| **Hardik Raval** | Customer Experience · Customer Success Specialist |
| **Rahul Bhardwaj** | Customer Experience · Customer Success Specialist |

Built as part of the **Cisco CX Innovation Hackathon 2026**.

---

## License

This project is licensed under the MIT License.

```
MIT License

Copyright (c) 2026 Hardik Raval, Rahul Bhardwaj

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

*Generated with ❤️ by Claude Code · Cisco CX Innovation Hackathon 2026*
