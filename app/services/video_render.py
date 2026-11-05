"""Turn a story into a narrated slide video.

Speech comes from edge-tts (Microsoft's online neural voices, no key needed)
and the video from moviepy with the ffmpeg bundled by imageio-ffmpeg. This runs
in a child process (app.utils.isolated), so a hung encoder or runaway memory
costs one video, not the worker. Failures raise ValueError("voice") or
ValueError("render"), which cross the process boundary intact.
"""
import asyncio
import logging
import os
import textwrap

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 1280, 720
FPS = 6  # Slides are still images; a low frame rate keeps encoding fast.
BACKGROUND = (18, 20, 34)
MIN_SLIDE_SECONDS = 2.0
TTS_TIMEOUT_SECONDS = 180

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def resolve_font() -> str | None:
    """A TrueType font, or None to use Pillow's small built-in one."""
    return next((path for path in FONT_CANDIDATES if os.path.exists(path)), None)


def synthesize(text: str, out_path: str, voice: str) -> str:
    try:
        import edge_tts

        async def run():
            await asyncio.wait_for(edge_tts.Communicate(text, voice).save(out_path), TTS_TIMEOUT_SECONDS)

        asyncio.run(run())
    except Exception as exc:
        raise ValueError("voice") from exc
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise ValueError("voice")
    return out_path


def compose(slides: list[str], weights: list[int], audio_path: str, out_path: str) -> str:
    """Show each slide for a share of the narration proportional to its weight."""
    try:
        from moviepy import AudioFileClip, ColorClip, CompositeVideoClip, TextClip, concatenate_videoclips

        font = resolve_font()
        audio = AudioFileClip(audio_path)
        # Keep every slide readable by dropping trailing slides rather than flashing them.
        keep = max(1, min(len(slides), int(audio.duration // MIN_SLIDE_SECONDS)))
        slides, weights = slides[:keep], [max(1, w) for w in weights[:keep]]
        total = sum(weights)

        clips = []
        for index, (text, weight) in enumerate(zip(slides, weights, strict=True), 1):
            duration = audio.duration * weight / total
            background = ColorClip(size=(WIDTH, HEIGHT), color=BACKGROUND, duration=duration)
            body = TextClip(
                font=font,
                text=textwrap.fill(text, width=30),
                font_size=64 if index == 1 else 56,
                color="white",
                size=(int(WIDTH * 0.84), int(HEIGHT * 0.6)),
                method="caption",
                text_align="center",
                duration=duration,
            ).with_position("center")
            counter = TextClip(
                font=font, text=f"{index} / {len(slides)}", font_size=28,
                color="rgb(94,158,255)", margin=(8, 12), duration=duration,
            ).with_position((52, HEIGHT - 90))
            clips.append(CompositeVideoClip([background, body, counter], size=(WIDTH, HEIGHT)))

        video = concatenate_videoclips(clips, method="compose").with_audio(audio)
        video.write_videofile(
            out_path, fps=FPS, codec="libx264", audio_codec="aac",
            preset="veryfast", threads=2, logger=None,
        )
        video.close()
        audio.close()
    except Exception as exc:
        raise ValueError("render") from exc
    return out_path


def render_story_video(title: str, scenes: list[tuple[str, str]], out_dir: str, voice: str) -> str:
    """Record the narration and render the video. Returns the video's path."""
    narration = "\n\n".join([f"{title}."] + [text for _heading, text in scenes])
    audio = synthesize(narration, os.path.join(out_dir, "narration.mp3"), voice)
    slides = [title] + [heading for heading, _text in scenes]
    weights = [len(title.split())] + [len(text.split()) for _heading, text in scenes]
    return compose(slides, weights, audio, os.path.join(out_dir, "video.mp4"))
