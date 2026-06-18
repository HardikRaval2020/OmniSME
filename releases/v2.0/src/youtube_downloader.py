"""Download short YouTube video clips (first 2 min) using yt-dlp."""
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Callable, List, Optional

import yt_dlp

logger = logging.getLogger(__name__)
_MAX_SECONDS = 120  # target clip length; moviepy trims the background to this in merger

_VIDEO_SUFFIXES = {".mp4", ".webm", ".mkv", ".m4v", ".mov", ".ts"}

# Format preference: single progressive stream avoids yt-dlp merge failures.
# DASH streams (bestvideo+bestaudio) require ffmpeg merging and do not support
# range-based partial downloads reliably.
_FORMAT = "best[height<=720][ext=mp4]/best[height<=480]/best"


class YouTubeDownloader:
    """Download a short clip from each YouTube URL for use as background footage.

    Call cleanup() after the clips have been consumed (e.g. after merging) to
    remove the temporary directories created during download.
    """

    def __init__(self):
        self._temp_dirs: List[Path] = []

    def download_clips(
        self,
        urls: List[str],
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> List[Path]:
        clips: List[Path] = []
        for i, url in enumerate(urls, 1):
            url = url.strip()
            if not url:
                continue
            if status_callback:
                status_callback(f"Downloading clip {i}/{len(urls)}: {url[:60]}…")
            path = self._download_one(url)
            if path:
                logger.info("Clip ready: %s", path)
            else:
                logger.warning("Skipped (no clip downloaded): %s", url)
                if status_callback:
                    status_callback(
                        f"⚠️ Could not download clip {i}/{len(urls)} — "
                        "video may be age-restricted or unavailable."
                    )
            if path:
                clips.append(path)
        return clips

    def cleanup(self) -> None:
        for d in self._temp_dirs:
            shutil.rmtree(d, ignore_errors=True)
        self._temp_dirs.clear()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _download_one(self, url: str) -> Optional[Path]:
        """Try a range-capped download first; fall back to full download."""
        out_dir = Path(tempfile.mkdtemp(prefix="omnisme_yt_"))
        self._temp_dirs.append(out_dir)

        # Stage 1: range-capped download (faster, smaller file)
        path = self._try_download(url, out_dir, use_range=True)
        if path:
            return path

        # Stage 2: full download fallback (works for DASH and HLS streams that
        # don't support partial downloads)
        logger.info("Range download failed for %s — retrying without range cut", url)
        path = self._try_download(url, out_dir, use_range=False)
        return path

    def _try_download(self, url: str, out_dir: Path, use_range: bool) -> Optional[Path]:
        ydl_opts: dict = {
            "format": _FORMAT,
            "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
        }
        if use_range:
            ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(
                None, [(0, _MAX_SECONDS)]
            )
            ydl_opts["force_keyframes_at_cuts"] = True

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    return None
                vid_id = info.get("id", "video")
                ext = info.get("ext", "mp4")

                # Check expected path first
                candidate = out_dir / f"{vid_id}.{ext}"
                if candidate.exists() and candidate.stat().st_size > 0:
                    return candidate

                # yt-dlp may write a merged file with a different extension
                for f in sorted(out_dir.iterdir(), key=lambda p: p.stat().st_size, reverse=True):
                    if f.suffix in _VIDEO_SUFFIXES and f.stat().st_size > 0:
                        return f
        except Exception as exc:
            logger.warning("Download attempt failed (%s range=%s): %s", url, use_range, exc)
        return None
