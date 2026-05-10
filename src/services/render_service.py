from __future__ import annotations

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
    VideoFileClip,
    afx,
    concatenate_audioclips,
    concatenate_videoclips,
    vfx,
)


FONT_PATH = "C:/Windows/Fonts/impact.ttf"
FONT_SIZE_NORMAL = 100
FONT_SIZE_HOOK = 124
FONT_SIZE_HIGHLIGHT = 116
SUBTITLE_WIDTH = 920
SUBTITLE_Y_POS = 1400


class RenderService:
    def __init__(self, assets_dir: str, outputs_dir: str, fps: int = 30):
        self.assets_dir = assets_dir
        self.outputs_dir = outputs_dir
        self.fps = fps
        self.whisper_model = None

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
                print(f"  [RENDER] Voice segment {index} failed: {exc}")

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
        music_volume: float = 1.25,
    ) -> str | None:
        highlighted_words = highlighted_words or []
        print(f"\n  [RENDER] Compositing video... (music volume: {music_volume})")

        voice = AudioFileClip(audio_path)
        total_duration = voice.duration + 1.5
        fade_duration = 0.55
        clip_duration = (total_duration + (len(video_paths) - 1) * fade_duration) / len(video_paths)

        processed_clips = []
        for index, video_path in enumerate(video_paths):
            try:
                processed_clips.append(self._process_clip(video_path, clip_duration, is_opening=index == 0))
            except Exception as exc:
                print(f"  [RENDER] Clip processing failed ({video_path}): {exc}")

        if not processed_clips:
            return None

        final_video = self._crossfade_clips(processed_clips, fade_duration)
        if final_video.duration > total_duration:
            final_video = final_video.subclipped(0, total_duration)

        dark_overlay = ColorClip(size=(1080, 1920), color=(0, 0, 0)).with_duration(final_video.duration).with_opacity(0.34)
        subtitle_clips = self._create_subtitles(audio_path, highlighted_words)
        final_video = CompositeVideoClip([final_video, dark_overlay] + subtitle_clips, size=(1080, 1920))
        final_audio = self._mix_audio(voice, music_path, final_video.duration, music_volume)
        final_video = final_video.with_effects([vfx.FadeOut(1.0)]).with_audio(final_audio.with_effects([afx.AudioFadeOut(1.0)]))

        output_path = os.path.join(self.outputs_dir, output_filename)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        temp_output_path = self._build_temp_output_path(output_path)
        try:
            final_video.write_videofile(temp_output_path, fps=self.fps, codec="libx264", audio_codec="aac", threads=4, logger="bar")
            os.replace(temp_output_path, output_path)
            return output_path
        finally:
            if os.path.exists(temp_output_path):
                try:
                    os.remove(temp_output_path)
                except OSError:
                    pass
            voice.close()
            final_video.close()
            final_audio.close()
            for clip in processed_clips:
                clip.close()

    def _build_temp_output_path(self, output_path: str) -> str:
        directory = os.path.dirname(output_path)
        name, extension = os.path.splitext(os.path.basename(output_path))
        return os.path.join(directory, f"{name}.rendering{extension}")

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
                    print(f"  [RENDER] Subtitle word failed ({word_text}): {exc}")
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
                font = ImageFont.truetype(FONT_PATH, size)
            except OSError:
                return ImageFont.load_default()
            width = font.getbbox(display_text)[2] - font.getbbox(display_text)[0]
            if width <= SUBTITLE_WIDTH - 32:
                return font
            size -= 6
        try:
            return ImageFont.truetype(FONT_PATH, 64)
        except OSError:
            return ImageFont.load_default()

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

    def _mix_audio(self, voice_clip, music_path: str | None, total_duration: float, music_volume: float = 1.25):
        layers = [voice_clip.with_start(0.5)]
        if not music_path:
            print("  [RENDER] No background music path; audio will be voiceover only.", flush=True)
            return CompositeAudioClip(layers)

        if not os.path.exists(music_path):
            print(f"  [RENDER] Background music file not found: {music_path}", flush=True)
            return CompositeAudioClip(layers)

        try:
            bg = AudioFileClip(music_path)
            if bg.duration < total_duration:
                bg = concatenate_audioclips([bg] * (int(total_duration / bg.duration) + 1))
            layers.append(bg.subclipped(0, total_duration).with_volume_scaled(music_volume))
            print(f"  [RENDER] Background music mixed: {music_path}", flush=True)
        except Exception as exc:
            print(f"  [RENDER] Background music mix failed: {exc}", flush=True)
        return CompositeAudioClip(layers)
