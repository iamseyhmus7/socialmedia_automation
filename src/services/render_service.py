from __future__ import annotations

import logging
import math
import os
import re

import edge_tts
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    ImageSequenceClip,
    VideoFileClip,
    afx,
    concatenate_audioclips,
    concatenate_videoclips,
    vfx,
)

logger = logging.getLogger(__name__)


FONT_PATH = os.getenv("SUBTITLE_FONT_PATH", "C:/Windows/Fonts/impact.ttf")
FONT_CANDIDATES = [
    FONT_PATH,
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
]
CTA_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    FONT_PATH,
]
FONT_SIZE_NORMAL = 100
FONT_SIZE_HOOK = 124
FONT_SIZE_HIGHLIGHT = 116
SUBTITLE_WIDTH = 920
SUBTITLE_Y_POS = 1400
CTA_MID_START = 6.5
CTA_MID_DURATION = 2.2
CTA_FINAL_DURATION = 2.4
CTA_ANIMATION_FPS = 15
CTA_PROFILE_NAME = os.getenv("CTA_PROFILE_NAME", "Risee Motivationn")
CTA_SUBSCRIBE_TEXT = os.getenv("CTA_SUBSCRIBE_TEXT", "ABONE OL")
CTA_SUBSCRIBED_TEXT = os.getenv("CTA_SUBSCRIBED_TEXT", "ABONE OLUNDU")
CTA_PROFILE_IMAGE = os.getenv("CTA_PROFILE_IMAGE", "user_data/channel_profile.jpg")


class RenderService:
    def __init__(self, assets_dir: str, outputs_dir: str, fps: int = 30):
        self.assets_dir = assets_dir
        self.outputs_dir = outputs_dir
        self.fps = fps
        self.whisper_model = None
        self.cta_profile_image = self._resolve_cta_profile_image()
        self.cleanup_stale_render_files()

    async def generate_voiceover(self, script_text: str, filename: str, highlighted_words: list[str] | None = None) -> str | None:
        highlighted_words = highlighted_words or []
        sentences = self._parse_sentences(script_text, highlighted_words)
        if not sentences:
            return None

        segment_audio_files = []
        for index, (text, intensity) in enumerate(sentences):
            rate = "+5%" if intensity == "INTENSE" else "-10%"
            pitch = "+2Hz" if intensity == "INTENSE" else "-5Hz"
            volume = "+30%" if intensity == "INTENSE" else "+0%"
            segment_file = os.path.join(self.assets_dir, f"_seg_{index}.mp3")
            try:
                communicate = edge_tts.Communicate(text, "en-US-BrianNeural", rate=rate, pitch=pitch, volume=volume)
                await communicate.save(segment_file)
                segment_audio_files.append(segment_file)
            except Exception as exc:
                logger.warning("Voice segment %s failed: %s", index, exc)

        if not segment_audio_files:
            return None

        final_path = os.path.join(self.assets_dir, filename)
        audio_clips = [AudioFileClip(path) for path in segment_audio_files]
        try:
            combined = concatenate_audioclips(audio_clips)
            combined.write_audiofile(final_path, logger=None)
            combined.close()
            return final_path
        finally:
            for clip in audio_clips:
                clip.close()
            for path in segment_audio_files:
                try:
                    os.remove(path)
                except OSError:
                    pass

    def create_video(
        self,
        video_paths: list[str],
        audio_path: str,
        music_path: str | None,
        script_text: str,
        output_filename: str,
        highlighted_words: list[str] | None = None,
        music_volume: float = 1.00,
    ) -> str | None:
        highlighted_words = highlighted_words or []
        logger.info("Compositing video music_volume=%s", music_volume)

        voice = AudioFileClip(audio_path)
        total_duration = voice.duration + 1.5
        fade_duration = 0.55
        clip_duration = (total_duration + (len(video_paths) - 1) * fade_duration) / len(video_paths)

        processed_clips = []
        for index, video_path in enumerate(video_paths):
            try:
                processed_clips.append(self._process_clip(video_path, clip_duration, is_opening=index == 0))
            except Exception as exc:
                logger.warning("Clip processing failed path=%s error=%s", video_path, exc)

        if not processed_clips:
            return None

        final_video = self._crossfade_clips(processed_clips, fade_duration)
        if final_video.duration > total_duration:
            final_video = final_video.subclipped(0, total_duration)

        dark_overlay = ColorClip(size=(1080, 1920), color=(0, 0, 0)).with_duration(final_video.duration).with_opacity(0.34)
        subtitle_clips = self._create_subtitles(audio_path, highlighted_words)
        cta_clips = self._create_call_to_action_clips(final_video.duration)
        final_video = CompositeVideoClip([final_video, dark_overlay] + subtitle_clips + cta_clips, size=(1080, 1920))
        final_audio = self._mix_audio(voice, music_path, final_video.duration, music_volume)
        final_video = final_video.with_effects([vfx.FadeOut(1.0)]).with_audio(final_audio.with_effects([afx.AudioFadeOut(1.0)]))

        output_path = os.path.join(self.outputs_dir, output_filename)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        temp_output_path = self._build_temp_output_path(output_path)
        try:
            self._remove_file_if_exists(temp_output_path)
            final_video.write_videofile(temp_output_path, fps=self.fps, codec="libx264", audio_codec="aac", threads=4, logger="bar")
            self._validate_render_output(temp_output_path, minimum_duration=max(total_duration - 1.0, 0.5))
            os.replace(temp_output_path, output_path)
            self._validate_render_output(output_path, minimum_duration=max(total_duration - 1.0, 0.5))
            return output_path
        finally:
            self._remove_file_if_exists(temp_output_path)
            voice.close()
            final_video.close()
            final_audio.close()
            for clip in processed_clips:
                clip.close()

    def _build_temp_output_path(self, output_path: str) -> str:
        directory = os.path.dirname(output_path)
        name, extension = os.path.splitext(os.path.basename(output_path))
        return os.path.join(directory, f"{name}.rendering{extension}")

    def cleanup_stale_render_files(self) -> int:
        if not os.path.isdir(self.outputs_dir):
            return 0

        removed = 0
        for root, _dirs, files in os.walk(self.outputs_dir):
            for file_name in files:
                if ".rendering" not in file_name:
                    continue
                path = os.path.join(root, file_name)
                if self._remove_file_if_exists(path):
                    removed += 1
        if removed:
            logger.info("Removed %s stale render temp files", removed)
        return removed

    def _resolve_cta_profile_image(self) -> str | None:
        candidates = []
        if CTA_PROFILE_IMAGE:
            candidates.append(CTA_PROFILE_IMAGE)
            if not os.path.isabs(CTA_PROFILE_IMAGE):
                candidates.append(os.path.join(os.getcwd(), CTA_PROFILE_IMAGE))
                candidates.append(os.path.join(os.path.dirname(self.assets_dir), CTA_PROFILE_IMAGE))
                candidates.append(os.path.join(self.assets_dir, os.path.basename(CTA_PROFILE_IMAGE)))
        candidates.append(os.path.join(os.path.dirname(self.assets_dir), "user_data", "channel_profile.jpg"))
        candidates.append(os.path.join(self.assets_dir, "channel_profile.jpg"))

        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None

    def _validate_render_output(self, output_path: str, minimum_duration: float = 0.5) -> None:
        if not os.path.exists(output_path):
            raise RuntimeError(f"Render output was not created: {output_path}")
        if os.path.getsize(output_path) <= 0:
            raise RuntimeError(f"Render output is empty: {output_path}")

        clip = VideoFileClip(output_path)
        try:
            if clip.duration < minimum_duration:
                raise RuntimeError(
                    f"Render output is too short: {clip.duration:.2f}s < {minimum_duration:.2f}s"
                )
            if clip.w != 1080 or clip.h != 1920:
                raise RuntimeError(f"Render output has invalid size: {clip.w}x{clip.h}")
            if clip.audio is None:
                raise RuntimeError("Render output has no audio track.")
        finally:
            clip.close()

    def _remove_file_if_exists(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        try:
            os.remove(path)
            return True
        except OSError as exc:
            logger.warning("Could not remove file path=%s error=%s", path, exc)
            return False

    def _parse_sentences(self, script_text: str, highlighted_words: list[str]) -> list[tuple[str, str]]:
        sentences = []
        for line in script_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            intensity = "INTENSE" if any(word.lower() in line.lower() for word in highlighted_words) else "NORMAL"
            sentences.append((line, intensity))
        if sentences:
            last_text, _ = sentences[-1]
            sentences[-1] = (last_text, "INTENSE")
        return sentences

    def _get_whisper_model(self):
        if self.whisper_model is None:
            from faster_whisper import WhisperModel
            self.whisper_model = WhisperModel("base.en", device="cpu", compute_type="int8")
        return self.whisper_model

    def _create_subtitles(self, audio_path: str, highlighted_words: list[str]) -> list:
        model = self._get_whisper_model()
        segments, _ = model.transcribe(audio_path, word_timestamps=True)
        subtitle_clips = []
        audio_delay = 0.35
        for segment in segments:
            for word in segment.words:
                word_text = word.word.strip()
                if not word_text:
                    continue
                duration = max(word.end - word.start, 0.15)
                try:
                    is_hook_word = word.start < 2.2
                    text_img = self._create_text_image(word_text, highlighted_words, is_hook_word=is_hook_word)
                    txt_clip = (
                        ImageClip(text_img, transparent=True)
                        .with_position(("center", SUBTITLE_Y_POS))
                        .with_start(word.start + audio_delay)
                        .with_duration(duration)
                    )
                    subtitle_clips.append(txt_clip)
                except Exception as exc:
                    logger.warning("Subtitle word failed word=%s error=%s", word_text, exc)
        return subtitle_clips

    def _create_text_image(self, text: str, highlighted_words: list[str], is_hook_word: bool = False):
        clean_display = re.sub(r"[^\w\s]", "", text.upper())
        highlighted = [word.upper() for word in highlighted_words]
        is_highlight = any(clean_display == value for value in highlighted)
        font_size = FONT_SIZE_HOOK if is_hook_word else FONT_SIZE_HIGHLIGHT if is_highlight else FONT_SIZE_NORMAL
        display_text = text.upper()
        words = display_text.split()
        font = self._fit_subtitle_font(display_text, font_size)
        space_width = font.getbbox(" ")[2] - font.getbbox(" ")[0]
        line_width = sum(font.getbbox(word)[2] - font.getbbox(word)[0] for word in words) + space_width * (len(words) - 1)
        line_height = font.getbbox(display_text)[3] - font.getbbox(display_text)[1]

        image = Image.new("RGBA", (SUBTITLE_WIDTH, line_height + 40), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        x_offset = (SUBTITLE_WIDTH - line_width) // 2
        for word in words:
            clean_word = re.sub(r"[^\w\s]", "", word)
            word_is_highlight = any(clean_word == value for value in highlighted)
            color = (255, 216, 56) if word_is_highlight else (255, 255, 255)
            stroke = 4 if is_hook_word or word_is_highlight else 2
            for dx, dy in [(-stroke, -stroke), (-stroke, stroke), (stroke, -stroke), (stroke, stroke)]:
                draw.text((x_offset + dx, 20 + dy), word, font=font, fill=(0, 0, 0, 255))
            draw.text((x_offset, 20), word, font=font, fill=color + (255,))
            x_offset += (font.getbbox(word)[2] - font.getbbox(word)[0]) + space_width
        return np.array(image)

    def _fit_subtitle_font(self, display_text: str, preferred_size: int):
        size = preferred_size
        while size >= 64:
            try:
                font = self._load_subtitle_font(size)
            except OSError:
                return ImageFont.load_default()
            width = font.getbbox(display_text)[2] - font.getbbox(display_text)[0]
            if width <= SUBTITLE_WIDTH - 32:
                return font
            size -= 6
        try:
            return self._load_subtitle_font(64)
        except OSError:
            return ImageFont.load_default()

    def _load_subtitle_font(self, size: int):
        for font_path in FONT_CANDIDATES:
            if font_path and os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
        raise OSError("No subtitle font found. Set SUBTITLE_FONT_PATH or install a bold TrueType font.")

    def _create_call_to_action_clips(self, video_duration: float) -> list:
        clips = []

        mid_start = CTA_MID_START
        if video_duration < CTA_MID_START + CTA_MID_DURATION + CTA_FINAL_DURATION:
            mid_start = max(1.2, video_duration * 0.42)
        mid_duration = min(CTA_MID_DURATION, max(video_duration - mid_start - 0.2, 0.1))
        if mid_duration >= 0.6:
            mid_clip = (
                self._create_subscribe_animation_clip(mid_duration)
                .with_start(mid_start)
                .with_position(lambda t: ("center", int(950 + 18 * (1 - self._cta_ease_out(min(t / 0.25, 1.0))))))
            )
            clips.append(mid_clip)

        final_duration = min(CTA_FINAL_DURATION, max(video_duration, 0.1))
        final_start = max(video_duration - final_duration, 0)
        final_clip = (
            self._create_final_call_to_action_clip(final_duration)
            .with_start(final_start)
            .with_position((0, 0))
        )
        clips.append(final_clip)
        return clips

    def _create_subscribe_animation_clip(self, duration: float):
        frame_count = max(1, int(duration * CTA_ANIMATION_FPS))
        frames = [
            self._create_subscribe_animation_frame(index / max(frame_count - 1, 1), include_like=False)
            for index in range(frame_count)
        ]
        return self._image_sequence_clip(frames, duration)

    def _create_final_call_to_action_clip(self, duration: float):
        frame_count = max(1, int(duration * CTA_ANIMATION_FPS))
        frames = [
            self._create_channel_end_screen_frame(index / max(frame_count - 1, 1))
            for index in range(frame_count)
        ]
        return self._image_sequence_clip(frames, duration)

    def _create_channel_end_screen_frame(self, progress: float):
        width, height = 1080, 1920
        scale = 2
        image = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 245))
        draw = ImageDraw.Draw(image)
        s = lambda value: int(value * scale)

        alpha = int(255 * min(progress / 0.18, 1.0) * min((1 - progress) / 0.12, 1.0))
        enter = self._cta_ease_out(min(progress / 0.28, 1.0))
        y_offset = int((1 - enter) * 70)
        click = min(max((progress - 0.42) / 0.18, 0.0), 1.0)
        settled = progress >= 0.52

        self._draw_channel_avatar(image, draw, s, width // 2, 610 + y_offset, progress)

        title_font = self._load_cta_font(62 * scale)
        channel_name = CTA_PROFILE_NAME.upper()[:24]
        title_y = 870 + y_offset
        self._draw_centered_text(draw, channel_name, title_font, s(width // 2), s(title_y), (255, 255, 255, 255), stroke_width=s(1))

        button_x, button_y = 170, 1030 + y_offset
        button_w, button_h = 740, 106
        button_fill = (244, 36, 54, 255)
        draw.rounded_rectangle((s(button_x), s(button_y), s(button_x + button_w), s(button_y + button_h)), radius=s(13), fill=button_fill)
        if settled:
            self._draw_checkmark(draw, s, button_x + 88, button_y + 55)
            label = CTA_SUBSCRIBED_TEXT
        else:
            label = CTA_SUBSCRIBE_TEXT
        button_font = self._load_cta_font((48 if settled else 53) * scale)
        self._draw_centered_text(draw, label, button_font, s(button_x + button_w // 2 + 22), s(button_y + 21), (255, 255, 255, 255), stroke_width=0)

        bell_x = button_x + button_w + 88
        bell_y = button_y + 52
        bell_tilt = math.sin(progress * math.pi * 18) * 9 if progress > 0.52 else -14 + 14 * click
        self._draw_end_screen_bell(draw, s, bell_x, bell_y, bell_tilt)

        cursor_start = (button_x + 470, button_y + 170)
        cursor_end = (button_x + 493, button_y + 69)
        cursor_travel = self._cta_ease_out(min(max((progress - 0.28) / 0.22, 0.0), 1.0))
        cursor_x = int(cursor_start[0] + (cursor_end[0] - cursor_start[0]) * cursor_travel)
        cursor_y = int(cursor_start[1] + (cursor_end[1] - cursor_start[1]) * cursor_travel)
        cursor_press = 1 - 0.18 * math.sin(min(click, 1.0) * math.pi)
        if progress < 0.78:
            self._draw_hand_cursor(draw, s, cursor_x, cursor_y, cursor_press)

        if 0.42 <= progress <= 0.70:
            ring_progress = (progress - 0.42) / 0.28
            ring_radius = 18 + int(54 * ring_progress)
            ring_alpha = int(230 * (1 - ring_progress))
            draw.ellipse(
                (s(cursor_end[0] - ring_radius), s(cursor_end[1] - ring_radius), s(cursor_end[0] + ring_radius), s(cursor_end[1] + ring_radius)),
                outline=(255, 255, 255, ring_alpha),
                width=s(4),
            )

        if alpha < 255:
            image.putalpha(image.getchannel("A").point(lambda value: int(value * alpha / 255)))
        return np.array(image.resize((width, height), Image.LANCZOS))

    def _image_sequence_clip(self, frames: list[np.ndarray], duration: float):
        try:
            clip = ImageSequenceClip(frames, fps=CTA_ANIMATION_FPS, with_mask=True)
        except TypeError:
            clip = ImageSequenceClip(frames, fps=CTA_ANIMATION_FPS)
        return clip.with_duration(duration)

    def _create_subscribe_animation_frame(self, progress: float, include_like: bool = False):
        width, height = (920, 620) if include_like else (1040, 250)
        scale = 2
        image = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        s = lambda value: int(value * scale)
        eased_in = self._cta_ease_out(min(progress / 0.22, 1.0))
        alpha = int(255 * min(progress / 0.16, 1.0) * min((1 - progress) / 0.10, 1.0))
        vertical_offset = int((1 - eased_in) * 28)

        if include_like:
            self._draw_like_burst(draw, s, 460, 158 + vertical_offset, progress, scale)
            pill_y = 320 + vertical_offset
        else:
            pill_y = 34 + vertical_offset

        clicked = progress >= 0.58
        self._draw_subscribe_pill(image, draw, s, width, pill_y, progress, clicked, scale)
        if include_like:
            self._draw_action_footer(draw, s, width, 510 + vertical_offset, scale)

        if alpha < 255:
            image.putalpha(image.getchannel("A").point(lambda value: int(value * alpha / 255)))
        return np.array(image.resize((width, height), Image.LANCZOS))

    def _draw_subscribe_pill(self, image: Image.Image, draw: ImageDraw.ImageDraw, s, width: int, y: int, progress: float, clicked: bool, scale: int) -> None:
        pill_w, pill_h = 920, 128
        x = (width - pill_w) // 2
        draw.rounded_rectangle((s(x + 8), s(y + 12), s(x + pill_w + 8), s(y + pill_h + 12)), radius=s(64), fill=(0, 0, 0, 72))
        draw.rounded_rectangle((s(x), s(y), s(x + pill_w), s(y + pill_h)), radius=s(64), fill=(248, 248, 248, 255))
        self._draw_pill_avatar(image, draw, s, x + 76, y + 64)

        name_font = self._load_cta_font(30 * scale)
        button_font = self._load_cta_font((22 if clicked else 25) * scale)
        name = self._fit_text_to_width(CTA_PROFILE_NAME, name_font, s(300))
        draw.text((s(x + 152), s(y + 45)), name, font=name_font, fill=(24, 24, 24, 255))

        button_x, button_y, button_w, button_h = x + 612, y + 35, 194, 58
        button_scale = 0.92 if 0.58 <= progress <= 0.66 else 1.0
        scaled_w = int(button_w * button_scale)
        scaled_h = int(button_h * button_scale)
        bx = button_x + (button_w - scaled_w) // 2
        by = button_y + (button_h - scaled_h) // 2
        button_fill = (230, 18, 24, 255) if not clicked else (224, 224, 224, 255)
        button_text = "TAK\u0130P ET" if not clicked else "TAK\u0130P ED\u0130LD\u0130"
        text_fill = (255, 255, 255, 255) if not clicked else (38, 38, 38, 255)
        draw.rounded_rectangle((s(bx), s(by), s(bx + scaled_w), s(by + scaled_h)), radius=s(7), fill=button_fill)
        self._draw_centered_text(draw, button_text, button_font, s(button_x + button_w // 2), s(button_y + 14), text_fill, stroke_width=0)

        bell_x = x + 852
        bell_shift = int(math.sin(progress * math.pi * 16) * 4) if clicked else 0
        self._draw_bell(draw, s, bell_x + 14, y + 58 + bell_shift)
        if clicked:
            draw.arc((s(bell_x - 8), s(y + 30), s(bell_x + 48), s(y + 90)), 300, 30, fill=(22, 22, 22, 190), width=s(2))

        cursor_x, cursor_y = self._cursor_position(x, y, progress)
        self._draw_cursor(draw, s, cursor_x, cursor_y)
        if 0.58 <= progress <= 0.78:
            click_progress = (progress - 0.58) / 0.20
            radius = 12 + int(38 * click_progress)
            alpha = int(220 * (1 - click_progress))
            draw.ellipse(
                (s(button_x + 86 - radius), s(button_y + 29 - radius), s(button_x + 86 + radius), s(button_y + 29 + radius)),
                outline=(230, 18, 24, alpha),
                width=s(3),
            )

    def _draw_avatar(self, draw: ImageDraw.ImageDraw, s, center_x: int, center_y: int) -> None:
        draw.ellipse((s(center_x - 42), s(center_y - 42), s(center_x + 42), s(center_y + 42)), fill=(15, 15, 18, 255))
        draw.ellipse((s(center_x - 34), s(center_y - 34), s(center_x + 34), s(center_y + 34)), fill=(142, 52, 255, 255))
        draw.ellipse((s(center_x - 20), s(center_y - 20), s(center_x + 54), s(center_y + 54)), fill=(15, 15, 18, 255))
        draw.ellipse((s(center_x - 12), s(center_y - 12), s(center_x + 46), s(center_y + 46)), fill=(124, 36, 238, 255))
        draw.line((s(center_x - 24), s(center_y), s(center_x + 22), s(center_y)), fill=(15, 15, 18, 255), width=s(7))

    def _draw_pill_avatar(self, target, draw: ImageDraw.ImageDraw, s, center_x: int, center_y: int) -> None:
        radius = 43
        draw.ellipse((s(center_x - radius), s(center_y - radius), s(center_x + radius), s(center_y + radius)), fill=(18, 20, 24, 255))
        if self.cta_profile_image:
            avatar = self._load_circular_profile_avatar(s((radius - 5) * 2))
            if avatar is not None and hasattr(target, "alpha_composite"):
                target.alpha_composite(avatar, (s(center_x - radius + 5), s(center_y - radius + 5)))
                return
        self._draw_avatar(draw, s, center_x, center_y)

    def _draw_channel_avatar(self, image: Image.Image, draw: ImageDraw.ImageDraw, s, center_x: int, center_y: int, progress: float) -> None:
        pulse = 1 + 0.035 * math.sin(progress * math.pi * 4)
        outer = int(145 * pulse)
        inner = int(126 * pulse)
        draw.ellipse((s(center_x - outer), s(center_y - outer), s(center_x + outer), s(center_y + outer)), fill=(244, 36, 54, 255))
        draw.ellipse((s(center_x - inner), s(center_y - inner), s(center_x + inner), s(center_y + inner)), fill=(10, 12, 15, 255))

        if self.cta_profile_image:
            avatar = self._load_circular_profile_avatar(s(inner * 2))
            if avatar is not None:
                image.alpha_composite(avatar, (s(center_x - inner), s(center_y - inner)))
                return

        draw.ellipse((s(center_x - 112), s(center_y - 112), s(center_x + 112), s(center_y + 112)), fill=(142, 52, 255, 255))
        draw.ellipse((s(center_x - 70), s(center_y - 70), s(center_x + 122), s(center_y + 122)), fill=(15, 15, 18, 255))
        draw.ellipse((s(center_x - 50), s(center_y - 50), s(center_x + 98), s(center_y + 98)), fill=(124, 36, 238, 255))
        draw.line((s(center_x - 86), s(center_y - 4), s(center_x + 18), s(center_y - 4)), fill=(15, 15, 18, 255), width=s(22))

    def _load_circular_profile_avatar(self, size: int):
        try:
            source = Image.open(self.cta_profile_image).convert("RGBA")
        except Exception as exc:
            logger.warning("CTA profile image could not be loaded path=%s error=%s", self.cta_profile_image, exc)
            return None

        crop = self._crop_profile_dark_circle(source)
        avatar = crop.resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, size - 1, size - 1), fill=255)
        avatar.putalpha(mask)
        return avatar

    def _crop_profile_dark_circle(self, image: Image.Image) -> Image.Image:
        width, height = image.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        return image.crop((left, top, left + side, top + side))

    def _draw_checkmark(self, draw: ImageDraw.ImageDraw, s, x: int, y: int) -> None:
        draw.line((s(x - 34), s(y - 2), s(x - 10), s(y + 23)), fill=(255, 255, 255, 255), width=s(8))
        draw.line((s(x - 10), s(y + 23), s(x + 38), s(y - 30)), fill=(255, 255, 255, 255), width=s(8))

    def _draw_bell(self, draw: ImageDraw.ImageDraw, s, x: int, y: int) -> None:
        draw.pieslice((s(x - 13), s(y - 20), s(x + 13), s(y + 18)), 180, 360, fill=(22, 22, 22, 255))
        draw.rectangle((s(x - 13), s(y - 2), s(x + 13), s(y + 14)), fill=(22, 22, 22, 255))
        draw.rectangle((s(x - 18), s(y + 14), s(x + 18), s(y + 19)), fill=(22, 22, 22, 255))
        draw.ellipse((s(x - 5), s(y + 19), s(x + 5), s(y + 29)), fill=(22, 22, 22, 255))

    def _draw_end_screen_bell(self, draw: ImageDraw.ImageDraw, s, x: int, y: int, tilt: float) -> None:
        box_w, box_h = 112, 106
        draw.rounded_rectangle((s(x - box_w // 2), s(y - box_h // 2), s(x + box_w // 2), s(y + box_h // 2)), radius=s(14), fill=(58, 58, 60, 255))
        bell_layer = Image.new("RGBA", draw.im.size, (0, 0, 0, 0))
        bell_draw = ImageDraw.Draw(bell_layer)
        self._draw_large_bell(bell_draw, s, x, y)
        if abs(tilt) > 0.1:
            crop = bell_layer.crop((s(x - 70), s(y - 70), s(x + 70), s(y + 70)))
            rotated = crop.rotate(tilt, resample=Image.BICUBIC, center=(s(70), s(70)))
            bell_layer.alpha_composite(rotated, (s(x - 70), s(y - 70)))
        draw.bitmap((0, 0), bell_layer, fill=None)
        draw.arc((s(x - 38), s(y - 44), s(x - 8), s(y - 12)), 120, 230, fill=(255, 255, 255, 220), width=s(5))
        draw.arc((s(x + 8), s(y - 44), s(x + 38), s(y - 12)), 310, 60, fill=(255, 255, 255, 220), width=s(5))

    def _draw_large_bell(self, draw: ImageDraw.ImageDraw, s, x: int, y: int) -> None:
        draw.pieslice((s(x - 30), s(y - 42), s(x + 30), s(y + 34)), 180, 360, fill=(255, 255, 255, 255))
        draw.rectangle((s(x - 30), s(y - 5), s(x + 30), s(y + 28)), fill=(255, 255, 255, 255))
        draw.rectangle((s(x - 42), s(y + 28), s(x + 42), s(y + 40)), fill=(255, 255, 255, 255))
        draw.ellipse((s(x - 11), s(y + 39), s(x + 11), s(y + 62)), fill=(255, 255, 255, 255))

    def _draw_cursor(self, draw: ImageDraw.ImageDraw, s, x: int, y: int) -> None:
        points = [(x, y), (x, y + 58), (x + 14, y + 45), (x + 26, y + 74), (x + 42, y + 68), (x + 29, y + 40), (x + 48, y + 40)]
        draw.polygon([(s(px), s(py)) for px, py in points], fill=(255, 255, 255, 255), outline=(32, 32, 32, 255))
        draw.line((s(x + 14), s(y + 45), s(x + 29), s(y + 40)), fill=(32, 32, 32, 255), width=s(2))

    def _draw_hand_cursor(self, draw: ImageDraw.ImageDraw, s, x: int, y: int, press_scale: float = 1.0) -> None:
        y = int(y + (1 - press_scale) * 16)
        white = (255, 255, 255, 255)
        outline = (30, 30, 30, 255)
        draw.rounded_rectangle((s(x + 18), s(y - 86), s(x + 43), s(y + 28)), radius=s(12), fill=white, outline=outline, width=s(3))
        draw.rounded_rectangle((s(x + 42), s(y - 30), s(x + 66), s(y + 32)), radius=s(11), fill=white, outline=outline, width=s(3))
        draw.rounded_rectangle((s(x + 63), s(y - 20), s(x + 86), s(y + 34)), radius=s(11), fill=white, outline=outline, width=s(3))
        draw.rounded_rectangle((s(x + 82), s(y - 10), s(x + 104), s(y + 30)), radius=s(10), fill=white, outline=outline, width=s(3))
        draw.polygon(
            [(s(x + 18), s(y + 12)), (s(x - 14), s(y - 22)), (s(x - 4), s(y - 42)), (s(x + 22), s(y - 16)), (s(x + 34), s(y + 22))],
            fill=white,
        )
        draw.line((s(x - 14), s(y - 22), s(x - 4), s(y - 42), s(x + 22), s(y - 16)), fill=outline, width=s(3))

    def _cursor_position(self, pill_x: int, pill_y: int, progress: float) -> tuple[int, int]:
        start = (pill_x + 660, pill_y + 102)
        end = (pill_x + 698, pill_y + 68)
        travel = min(max((progress - 0.28) / 0.28, 0.0), 1.0)
        travel = self._cta_ease_out(travel)
        return (
            int(start[0] + (end[0] - start[0]) * travel),
            int(start[1] + (end[1] - start[1]) * travel),
        )

    def _draw_like_burst(self, draw: ImageDraw.ImageDraw, s, center_x: int, center_y: int, progress: float, scale: int) -> None:
        pop = self._cta_ease_out(min(progress / 0.35, 1.0))
        radius = int(82 + 18 * pop)
        draw.ellipse((s(center_x - radius), s(center_y - radius), s(center_x + radius), s(center_y + radius)), fill=(255, 255, 255, 245))
        for index in range(14):
            angle = (math.tau / 14) * index + progress * 0.7
            particle_radius = 104 + int(34 * min(progress, 0.8))
            px = center_x + math.cos(angle) * particle_radius
            py = center_y + math.sin(angle) * particle_radius
            color = (230, 18, 24, 255) if index % 2 else (50, 103, 236, 255)
            draw.ellipse((s(px - 7), s(py - 7), s(px + 7), s(py + 7)), fill=color)
        self._draw_thumb(draw, s, center_x, center_y + 4, 1.05 + 0.12 * math.sin(progress * math.pi * 2))
        cursor_x = center_x + 34
        cursor_y = center_y + 48 - int(16 * self._cta_ease_out(min(progress / 0.45, 1.0)))
        self._draw_cursor(draw, s, cursor_x, cursor_y)

    def _draw_thumb(self, draw: ImageDraw.ImageDraw, s, center_x: int, center_y: int, scale_factor: float) -> None:
        def sx(value: float) -> int:
            return s(center_x + int(value * scale_factor))

        def sy(value: float) -> int:
            return s(center_y + int(value * scale_factor))

        blue = (50, 103, 236, 255)
        draw.rounded_rectangle((sx(-72), sy(-18), sx(-30), sy(70)), radius=s(8), fill=blue)
        draw.polygon(
            [
                (sx(-18), sy(68)),
                (sx(-18), sy(-24)),
                (sx(14), sy(-60)),
                (sx(24), sy(-118)),
                (sx(48), sy(-116)),
                (sx(54), sy(-48)),
                (sx(92), sy(-40)),
                (sx(112), sy(-14)),
                (sx(100), sy(56)),
                (sx(60), sy(78)),
            ],
            fill=blue,
        )

    def _draw_action_footer(self, draw: ImageDraw.ImageDraw, s, width: int, y: int, scale: int) -> None:
        font = self._load_cta_font(24 * scale)
        text = "BE\u011eEN  \u2022  TAK\u0130P ET  \u2022  PAYLA\u015e  \u2022  YORUM YAP"
        bbox = draw.textbbox((0, 0), text, font=font)
        x = (width * scale - (bbox[2] - bbox[0])) // 2
        draw.rounded_rectangle((s(100), s(y - 14), s(width - 100), s(y + 50)), radius=s(32), fill=(0, 0, 0, 168))
        draw.text((x, s(y)), text, font=font, fill=(255, 255, 255, 235))

    def _draw_centered_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font,
        center_x: int,
        y: int,
        fill: tuple[int, int, int, int],
        stroke_width: int = 1,
    ) -> None:
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        width = bbox[2] - bbox[0]
        draw.text(
            (center_x - width // 2, y),
            text,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 180),
        )

    def _load_cta_font(self, size: int):
        for font_path in CTA_FONT_CANDIDATES:
            if font_path and os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
        return ImageFont.load_default()

    def _fit_text_to_width(self, text: str, font, max_width: int) -> str:
        if font.getbbox(text)[2] - font.getbbox(text)[0] <= max_width:
            return text
        ellipsis = "..."
        value = text
        while value and font.getbbox(value + ellipsis)[2] - font.getbbox(value + ellipsis)[0] > max_width:
            value = value[:-1]
        return (value.rstrip() + ellipsis) if value else text[:1]

    def _cta_ease_out(self, value: float) -> float:
        return 1 - (1 - value) ** 3

    def _process_clip(self, video_path: str, target_duration: float, is_opening: bool = False):
        clip = VideoFileClip(video_path)
        if clip.duration < target_duration:
            clip = concatenate_videoclips([clip] * (int(target_duration / clip.duration) + 1), method="compose")
        clip = clip.subclipped(0, target_duration).resized(height=1920)

        if clip.w > 1080:
            clip = clip.cropped(x1=clip.w / 2 - 540, y1=0, x2=clip.w / 2 + 540, y2=1920)
        else:
            clip = clip.resized(width=1080).cropped(x1=0, y1=0, x2=1080, y2=1920)
        zoom_ratio = 0.16 if is_opening else 0.075
        return self._apply_ken_burns(clip, zoom_ratio=zoom_ratio)

    def _apply_ken_burns(self, clip, zoom_ratio: float = 0.05):
        width, height = clip.size

        def zoom_effect(get_frame, t):
            zoom = 1 + (zoom_ratio * (t / clip.duration))
            frame = get_frame(t)
            image = Image.fromarray(frame).resize((int(width * zoom), int(height * zoom)), Image.LANCZOS)
            x, y = (image.width - width) // 2, (image.height - height) // 2
            return np.array(image.crop((x, y, x + width, y + height)))

        return clip.transform(zoom_effect)

    def _crossfade_clips(self, clips: list, fade_duration: float):
        faded = []
        for index, clip in enumerate(clips):
            if index == 0:
                faded.append(clip.with_effects([vfx.CrossFadeOut(fade_duration)]))
            elif index == len(clips) - 1:
                faded.append(clip.with_effects([vfx.CrossFadeIn(fade_duration)]))
            else:
                faded.append(clip.with_effects([vfx.CrossFadeIn(fade_duration), vfx.CrossFadeOut(fade_duration)]))
        return concatenate_videoclips(faded, padding=-fade_duration, method="compose")

    def _mix_audio(self, voice_clip, music_path: str | None, total_duration: float, music_volume: float = 1.00):
        layers = [voice_clip.with_start(0.5)]
        if not music_path:
            logger.info("No background music path; audio will be voiceover only")
            return CompositeAudioClip(layers)

        if not os.path.exists(music_path):
            logger.warning("Background music file not found: %s", music_path)
            return CompositeAudioClip(layers)

        try:
            bg = AudioFileClip(music_path)
            if bg.duration < total_duration:
                bg = concatenate_audioclips([bg] * (int(total_duration / bg.duration) + 1))
            layers.append(bg.subclipped(0, total_duration).with_volume_scaled(music_volume))
            logger.info("Background music mixed: %s", music_path)
        except Exception as exc:
            logger.warning("Background music mix failed: %s", exc)
        return CompositeAudioClip(layers)
