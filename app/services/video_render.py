"""Turn a story into a narrated slide video.

Speech comes from edge-tts (Microsoft's online neural voices, no key needed).
Slides are drawn with Pillow and joined with the narration by the ffmpeg
binary bundled in imageio-ffmpeg. This runs in a child process
(app.utils.isolated), so a hung encoder or runaway memory costs one video,
not the worker. Failures raise ValueError("voice") or ValueError("render"),
which cross the process boundary intact.
"""
import asyncio
import os
import re
import subprocess
import textwrap

from app.services.speech import display_name, speakable

WIDTH, HEIGHT = 1280, 720
FPS = 6  # Slides are still images; a low frame rate keeps encoding fast.
BACKGROUND = (18, 20, 34)
ACCENT = (242, 160, 61)
COUNTER = (94, 158, 255)
MIN_SLIDE_SECONDS = 2.0
TTS_TIMEOUT_SECONDS = 180
ENCODE_TIMEOUT_SECONDS = 600

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def resolve_font() -> str | None:
    """A TrueType font, or None to use Pillow's built-in one."""
    return next((path for path in FONT_CANDIDATES if os.path.exists(path)), None)


def _ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


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


def audio_seconds(path: str) -> float:
    """The length of an audio file, read from ffmpeg's report."""
    probe = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True, timeout=60
    )
    match = _DURATION.search(probe.stderr)
    if not match:
        raise ValueError("render")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _font(path: str | None, size: int):
    from PIL import ImageFont

    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size=size)


def draw_slide(text: str, index: int, total: int, font_path: str | None, out_path: str) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    size = 64 if index == 1 else 56
    font = _font(font_path, size)
    lines = textwrap.wrap(text, width=30)[:6] or [""]
    spacing = int(size * 0.35)
    heights = [draw.textbbox((0, 0), line, font=font)[3] for line in lines]
    block = sum(heights) + spacing * (len(lines) - 1)
    y = (HEIGHT - block) // 2
    for line, height in zip(lines, heights, strict=True):
        width = draw.textlength(line, font=font)
        draw.text(((WIDTH - width) / 2, y), line, font=font, fill="white")
        y += height + spacing
    draw.rectangle([(WIDTH - 220) // 2, y + 18, (WIDTH + 220) // 2, y + 24], fill=ACCENT)
    draw.text((60, HEIGHT - 80), f"{index} / {total}", font=_font(font_path, 28), fill=COUNTER)
    image.save(out_path)


def compose(slides: list[str], weights: list[int], audio_path: str, out_path: str) -> str:
    """Show each slide for a share of the narration proportional to its weight."""
    try:
        duration = audio_seconds(audio_path)
        # Keep every slide readable by dropping trailing slides rather than flashing them.
        keep = max(1, min(len(slides), int(duration // MIN_SLIDE_SECONDS)))
        slides, weights = slides[:keep], [max(1, w) for w in weights[:keep]]
        total = sum(weights)

        folder = os.path.dirname(os.path.abspath(out_path))
        font = resolve_font()
        entries = []
        for index, (text, weight) in enumerate(zip(slides, weights, strict=True), 1):
            image = os.path.join(folder, f"slide-{index:02d}.png")
            draw_slide(text, index, len(slides), font, image)
            entries.append((image, duration * weight / total))

        # The concat demuxer needs the last image listed twice to honour its duration.
        listing = os.path.join(folder, "slides.txt")
        with open(listing, "w", encoding="utf-8") as handle:
            for image, seconds in entries:
                handle.write(f"file '{image.replace(os.sep, '/')}'\nduration {seconds:.3f}\n")
            handle.write(f"file '{entries[-1][0].replace(os.sep, '/')}'\n")

        subprocess.run(
            [
                _ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                "-f", "concat", "-safe", "0", "-i", listing,
                "-i", audio_path,
                "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest",
                "-movflags", "+faststart", out_path,
            ],
            check=True, capture_output=True, timeout=ENCODE_TIMEOUT_SECONDS,
        )
        for image, _seconds in entries:
            os.remove(image)
        os.remove(listing)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("render") from exc
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise ValueError("render")
    return out_path


def render_story_video(title: str, scenes: list[tuple[str, str]], out_dir: str, voice: str) -> str:
    """Record the narration and render the video. Returns the video's path."""
    narration = speakable("\n\n".join([f"{title}."] + [text for _heading, text in scenes]))
    audio = synthesize(narration, os.path.join(out_dir, "narration.mp3"), voice)
    slides = [display_name(title)] + [display_name(heading) for heading, _text in scenes]
    weights = [len(title.split())] + [len(text.split()) for _heading, text in scenes]
    return compose(slides, weights, audio, os.path.join(out_dir, "video.mp4"))
