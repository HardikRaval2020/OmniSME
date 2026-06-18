"""Merge HeyGen avatar video with YouTube clips in picture-in-picture layout."""
import logging
import time
from pathlib import Path
from typing import List

import PIL.Image

# moviepy 1.x uses Image.ANTIALIAS which was removed in Pillow 10.0.
# Restore the alias so moviepy works without downgrading Pillow.
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

logger = logging.getLogger(__name__)

OUTPUT_W, OUTPUT_H = 1280, 720
PIP_W_RATIO = 0.28  # avatar pip occupies 28 % of output width


class VideoMerger:
    """Compose a final MP4: YouTube clips as full-screen background, avatar in bottom-right PiP."""

    def merge(self, avatar_path: Path, youtube_clips: List[Path], topic: str) -> Path:
        try:
            from moviepy.editor import CompositeVideoClip, VideoFileClip
        except ImportError as exc:
            raise ImportError(
                "moviepy is required for PiP merging. Run: pip install 'moviepy<2.0'"
            ) from exc

        output_dir = Path.home() / "output"
        output_dir.mkdir(exist_ok=True)
        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in topic)[:50]
        out_path = output_dir / f"{safe.strip().replace(' ', '_')}_{int(time.time())}.mp4"

        avatar = VideoFileClip(str(avatar_path))
        composite = None
        try:
            if youtube_clips:
                bg = self._build_background(youtube_clips, avatar.duration)
                pip_w = int(OUTPUT_W * PIP_W_RATIO)
                x_pos = OUTPUT_W - pip_w - 20
                y_pos = OUTPUT_H - int(pip_w * avatar.size[1] / avatar.size[0]) - 20

                avatar_pip = avatar.resize(width=pip_w).set_position((x_pos, y_pos))
                composite = CompositeVideoClip(
                    [bg, avatar_pip], size=(OUTPUT_W, OUTPUT_H)
                ).set_duration(avatar.duration)

                if avatar.audio is not None:
                    composite = composite.set_audio(avatar.audio)
                else:
                    logger.warning("Avatar video has no audio track; output will be silent.")
            else:
                composite = avatar

            composite.write_videofile(
                str(out_path), codec="libx264", audio_codec="aac", logger=None
            )
        finally:
            avatar.close()
            # composite may be the same object as avatar (Avatar Only path);
            # only close it separately when it is a distinct CompositeVideoClip.
            if composite is not None and composite is not avatar:
                composite.close()

        return out_path

    def _build_background(self, clip_paths: List[Path], target_dur: float):
        from moviepy.editor import VideoFileClip, concatenate_videoclips

        segments = []
        remaining = target_dur
        for path in clip_paths:
            if remaining <= 0:
                break
            clip = VideoFileClip(str(path)).without_audio()
            use = min(clip.duration, remaining)
            segments.append(clip.subclip(0, use).resize((OUTPUT_W, OUTPUT_H)))
            remaining -= use

        if not segments:
            raise ValueError("No valid YouTube clips to use as background.")

        bg = concatenate_videoclips(segments)

        # If clips are shorter than avatar, fill by re-opening the last source
        # file (NOT by reusing the same Python object — stateful ffmpeg readers
        # cannot be shared across concatenate slots without frame corruption).
        while bg.duration < target_dur - 0.1:
            filler = VideoFileClip(str(clip_paths[-1])).without_audio()
            use = min(filler.duration, target_dur - bg.duration)
            filler_seg = filler.subclip(0, use).resize((OUTPUT_W, OUTPUT_H))
            bg = concatenate_videoclips([bg, filler_seg])

        return bg.subclip(0, target_dur)
