"""HeyGen REST API v2 wrapper — create, poll, and download avatar videos."""
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests


class HeyGenClient:
    BASE_URL = "https://api.heygen.com"
    _SLIDE_MAX_CHARS = 1400

    def __init__(self, api_key: str):
        self._headers = {
            "X-Api-Key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ── Avatar & voice discovery ─────────────────────────────────────────────

    def list_avatars(self) -> List[Dict]:
        resp = self._get_with_retry(f"{self.BASE_URL}/v2/avatars")
        return resp.json().get("data", {}).get("avatars", [])

    def list_voices(self, language: str = "English") -> List[Dict]:
        resp = self._get_with_retry(f"{self.BASE_URL}/v2/voices")
        voices = resp.json().get("data", {}).get("voices", [])
        return [v for v in voices if v.get("language", "").startswith(language)]

    def _get_with_retry(self, url: str, retries: int = 2, timeout: int = 30) -> requests.Response:
        last_exc: Exception = RuntimeError("No attempts made")
        for attempt in range(1, retries + 1):
            try:
                resp = requests.get(url, headers=self._headers, timeout=timeout)
                resp.raise_for_status()
                return resp
            except requests.exceptions.Timeout as exc:
                last_exc = exc
                if attempt < retries:
                    time.sleep(5 * attempt)
            except requests.exceptions.RequestException as exc:
                raise
        raise last_exc

    # ── Video generation ─────────────────────────────────────────────────────

    def create_video(self, script: str, avatar_id: str, voice_id: str) -> str:
        chunks = self._split_script(script)
        video_inputs = [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": avatar_id,
                    "avatar_style": "normal",
                },
                "voice": {
                    "type": "text",
                    "input_text": chunk,
                    "voice_id": voice_id,
                    "speed": 1.0,
                },
                "background": {"type": "color", "value": "#1a1a2e"},
            }
            for chunk in chunks
        ]

        payload = {
            "video_inputs": video_inputs,
            "dimension": {"width": 1280, "height": 720},
        }

        resp = requests.post(
            f"{self.BASE_URL}/v2/video/generate",
            json=payload,
            headers=self._headers,
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("error"):
            raise RuntimeError(f"HeyGen API error: {body['error']}")
        return body["data"]["video_id"]

    def poll_status(
        self,
        video_id: str,
        timeout: int = 1800,
        progress_callback: Optional[Callable[[float, int], None]] = None,
    ) -> str:
        start = time.time()
        while True:
            elapsed = time.time() - start
            if elapsed >= timeout:
                raise TimeoutError(
                    f"HeyGen video generation timed out after {int(timeout)}s "
                    f"(video_id={video_id}). The render may still be in progress — "
                    f"use 'Check Status' to resume."
                )

            resp = requests.get(
                f"{self.BASE_URL}/v1/video_status.get",
                params={"video_id": video_id},
                headers=self._headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            status = data.get("status", "")

            if progress_callback:
                progress_callback(min(elapsed / timeout, 0.95), int(elapsed))

            if status == "completed":
                video_url = data.get("video_url")
                if not video_url:
                    raise RuntimeError(
                        f"HeyGen returned 'completed' but no video_url "
                        f"(video_id={video_id}). Check your HeyGen dashboard."
                    )
                return video_url
            if status == "failed":
                raise RuntimeError(
                    f"HeyGen video generation failed: {data.get('error', 'unknown error')}"
                )

            # Adaptive interval: check frequently early on, ease off for long renders
            time.sleep(15 if elapsed < 120 else 30)

    # ── Download ─────────────────────────────────────────────────────────────

    def download_video(self, video_url: str, topic: str) -> Path:
        output_dir = Path.home() / "output"
        output_dir.mkdir(exist_ok=True)

        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in topic)
        safe = safe.strip().replace(" ", "_")[:50]
        filename = f"{safe}_{int(time.time())}.mp4"
        filepath = output_dir / filename

        resp = requests.get(video_url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(filepath, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=8192):
                fh.write(chunk)

        return filepath

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _split_script(self, script: str) -> List[str]:
        sentences = script.replace("\n", " ").split(". ")
        chunks: List[str] = []
        current = ""
        for sentence in sentences:
            # Strip trailing period before re-appending to avoid double-periods
            # when the source sentence already ends with one (e.g. "...summary.")
            piece = sentence.strip().rstrip(". ") + ". "
            if len(current) + len(piece) > self._SLIDE_MAX_CHARS and current:
                chunks.append(current.strip())
                current = piece
            else:
                current += piece
        if current.strip():
            chunks.append(current.strip())
        return chunks or [script[:self._SLIDE_MAX_CHARS]]
