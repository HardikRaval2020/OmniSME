"""Select script-section-aligned video segments using OpenAI embedding similarity."""
import logging
import re
from typing import Dict, List, Optional, Tuple

import numpy as np
from openai import OpenAI
from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)

# Typical AI-avatar speaking rate — used to estimate section duration from word count
_WORDS_PER_MINUTE = 130

# Matches numbered script section headers: "1. HOOK (30 seconds):" or "KEY POINT 1:"
_SECTION_RE = re.compile(
    r"^(?:\d+\.\s*)?([A-Z][A-Z ,&]+\d*)[\s:([]",
    re.MULTILINE,
)

_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|/embed/|/v/)([a-zA-Z0-9_-]{11})")


class SegmentSelector:
    """
    For each section of the generated script, find the most semantically
    similar 20-second window from source video transcripts using
    OpenAI text-embedding-3-small cosine similarity.

    Returns List[Tuple[url, src_start, src_end, avatar_section_duration_sec]]
    so the video merger can display each clip for exactly its matching section.
    """

    def __init__(self):
        self._openai = OpenAI()

    def get_relevant_segments(
        self,
        urls: List[str],
        topic: str,
        script: str = "",
        max_segments: int = 7,
        window_secs: int = 20,
    ) -> List[Tuple[str, float, float, float]]:
        """
        Return (url, src_start_sec, src_end_sec, avatar_duration_sec) — one tuple
        per script section, ordered to match the avatar narration timeline.
        """
        sections = self._parse_sections(script) if script else []
        if not sections:
            # No sections parsed — treat whole topic+script as one query
            sections = [{"title": "Script", "text": f"{topic} {script}".strip()}]

        sections = self._estimate_durations(sections)

        windows = self._build_all_windows(urls, window_secs)
        if not windows:
            logger.warning("No transcript windows found — segment selection skipped.")
            return []

        # Batch-embed all transcript windows in one API call
        logger.info("Embedding %d transcript windows via OpenAI…", len(windows))
        window_embeddings = self._embed_batch([w["text"] for w in windows])
        for w, emb in zip(windows, window_embeddings):
            w["embedding"] = emb

        chosen: List[Tuple[str, float, float, float]] = []
        used: set = set()

        for sec in sections[:max_segments]:
            # Embed the section text with topic prefix for better context
            query_emb = self._embed_single(f"{topic}: {sec['text']}")
            best_score, best_win = -1.0, None

            for w in windows:
                key = (w["url"], w["start"])
                if key in used:
                    continue
                score = _cosine(query_emb, w["embedding"])
                if score > best_score:
                    best_score, best_win = score, w

            if best_win is not None:
                used.add((best_win["url"], best_win["start"]))
                chosen.append(
                    (
                        best_win["url"],
                        best_win["start"],
                        best_win["end"],
                        sec["duration"],
                    )
                )
                logger.info(
                    "%-28s → %6.1f–%6.1fs  sim=%.3f",
                    sec["title"][:28],
                    best_win["start"],
                    best_win["end"],
                    best_score,
                )

        return chosen

    # ── Internal ──────────────────────────────────────────────────────────────

    def _parse_sections(self, script: str) -> List[Dict]:
        """Split GPT-4o script into titled sections using the numbered header format."""
        matches = list(_SECTION_RE.finditer(script))
        if not matches:
            return []
        sections = []
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(script)
            text = script[m.end() : end].strip()
            if text:
                sections.append({"title": m.group(1).strip(), "text": text})
        return sections

    def _estimate_durations(self, sections: List[Dict]) -> List[Dict]:
        """Estimate avatar speaking time per section from word count."""
        for s in sections:
            s["duration"] = (len(s["text"].split()) / _WORDS_PER_MINUTE) * 60
        return sections

    def _build_all_windows(self, urls: List[str], window_secs: int) -> List[Dict]:
        windows = []
        for url in urls:
            vid_id = self._extract_video_id(url.strip())
            if not vid_id:
                continue
            segs = self._fetch_transcript(vid_id)
            if not segs:
                continue
            windows.extend(self._slide_windows(url.strip(), segs, window_secs))
        return windows

    def _slide_windows(
        self, url: str, segs: List[Dict], window_secs: int
    ) -> List[Dict]:
        windows = []
        i = 0
        while i < len(segs):
            win_start = segs[i]["start"]
            parts: List[str] = []
            j = i
            while j < len(segs) and (segs[j]["start"] - win_start) < window_secs:
                parts.append(segs[j]["text"])
                j += 1
            text = " ".join(parts).strip()
            if text:
                last = segs[j - 1] if j > i else segs[i]
                win_end = last["start"] + last.get("duration", 3.0)
                windows.append(
                    {"url": url, "start": win_start, "end": win_end, "text": text}
                )
            i = j if j > i else i + 1
        return windows

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        results: List[List[float]] = []
        for i in range(0, len(texts), 100):
            batch = [t[:6000] for t in texts[i : i + 100]]
            resp = self._openai.embeddings.create(
                model="text-embedding-3-small", input=batch
            )
            results.extend(r.embedding for r in resp.data)
        return results

    def _embed_single(self, text: str) -> List[float]:
        resp = self._openai.embeddings.create(
            model="text-embedding-3-small", input=[text[:6000]]
        )
        return resp.data[0].embedding

    def _fetch_transcript(self, video_id: str) -> List[Dict]:
        try:
            return YouTubeTranscriptApi.get_transcript(
                video_id, languages=["en", "en-US", "en-GB"]
            )
        except Exception as exc:
            logger.warning("Transcript fetch failed for %s: %s", video_id, exc)
            return []

    def _extract_video_id(self, url: str) -> Optional[str]:
        m = _VIDEO_ID_RE.search(url)
        return m.group(1) if m else None


def _cosine(a: List[float], b: List[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom > 1e-9 else 0.0
