import os
import json
import subprocess
import numpy as np
import soundfile as sf
import librosa
import requests
from moviepy.editor import ImageSequenceClip, AudioFileClip
from PIL import Image


class CharEngine:

    def __init__(self, nvidia_api_key=""):

        self.conf = {
            "asset_path": "/mnt/android/_dl/py/video/chars/",
            "piper": {
                "path": "/root/_soft/piper/piper",
                "model_path": "/root/_soft/piper/models/",
                "models": {
                    "en-gb-vctk": {
                        "model": "en_GB-vctk-medium.onnx",
                        "cfg": "en_GB-vctk-medium.onnx.json",
                    },
                },
            },
            "nvidia": {
                "api_key": nvidia_api_key,
                "url": "https://build.nvidia.com/nvidia/magpie-tts-multilingual/api",
            },
        }

        self.characters = {
            "alice": {
                "tts": "nvidia",
                "voice_model": "Sofia",
                "pitch": 1.3,
                "speed": 1.2,
                "sprites": {
                    "mouth": {
                        "main": {"path": "alice/mouth/"},
                    },
                    "body": {
                        "main": {
                            "path": "alice/body/",
                            "mouth_pos": (400, 300),
                        },
                    },
                },
            },
            "rabbit": {
                "tts": "piper",
                "voice_model": "en-gb-vctk",
                "pitch": 0.7,
                "speed": 0.8,
                "sprites": {
                    "mouth": {
                        "main": {"path": "rabbit/mouth/"},
                    },
                    "body": {
                        "main": {
                            "path": "rabbit/body/",
                            "mouth_pos": (400, 300),
                        },
                    },
                },
            },
        }

    # =========================================================
    # AUDIO
    # =========================================================

    def generate_audio(self, text, mood, character, output_audio, output_timestamps):

        cfg = self.characters[character]

        if cfg["tts"] == "piper":
            self._tts_piper(text, cfg, output_audio)

        elif cfg["tts"] == "nvidia":
            self._tts_nvidia(text, cfg, output_audio)

        else:
            raise ValueError("Unknown TTS engine")

        self._process_voice(output_audio, cfg["pitch"], cfg["speed"])

        timestamps = self._fake_timestamps(text)

        with open(output_timestamps, "w") as f:
            json.dump(timestamps, f, indent=2)

    # ======================
    # PIPER
    # ======================

    def _tts_piper(self, text, char_cfg, output_audio):

        model_key = char_cfg["voice_model"]

        model_cfg = self.conf["piper"]["models"][model_key]

        model_path = os.path.join(
            self.conf["piper"]["model_path"],
            model_cfg["model"]
        )

        cfg_path = os.path.join(
            self.conf["piper"]["model_path"],
            model_cfg["cfg"]
        )

        cmd = [
            self.conf["piper"]["path"],
            "-m", model_path,
            "-c", cfg_path,
            "-f", output_audio
        ]

        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-8"))

    # ======================
    # NVIDIA MAGPIE
    # ======================

    def _tts_nvidia(self, text, char_cfg, output_audio):

        headers = {
            "Authorization": f"Bearer {self.conf['nvidia']['api_key']}",
            "Content-Type": "application/json",
        }

        payload = {
            "text": text,
            "voice": char_cfg["voice_model"],
        }

        r = requests.post(
            self.conf["nvidia"]["url"],
            headers=headers,
            json=payload
        )

        if r.status_code != 200:
            raise RuntimeError(r.text)

        with open(output_audio, "wb") as f:
            f.write(r.content)

    # ======================
    # VOICE POST PROCESS
    # ======================

    def _process_voice(self, path, pitch, speed):

        y, sr = librosa.load(path, sr=None)

        if pitch != 1.0:
            y = librosa.effects.pitch_shift(
                y, sr=sr, n_steps=(pitch - 1.0) * 12
            )

        if speed != 1.0:
            y = librosa.effects.time_stretch(y, rate=speed)

        sf.write(path, y, sr)

    # ======================
    # FAKE TIMESTAMPS
    # ======================

    def _fake_timestamps(self, text):

        words = text.split()
        timestamps = []

        t = 0.0

        for w in words:
            duration = max(0.15, len(w) * 0.05)

            timestamps.append({
                "word": w,
                "start": t,
                "end": t + duration
            })

            t += duration

        return timestamps

    # =========================================================
    # VIDEO
    # =========================================================

    def generate_lip_video(
        self,
        character,
        pose,
        timestamps_file,
        audio_file,
        output_video,
        fps=30
    ):

        cfg = self.characters[character]

        with open(timestamps_file) as f:
            timestamps = json.load(f)

        frames = []

        for ts in timestamps:
            frame = self._compose_frame(character, ts["word"])
            frames.append(frame)

        clip = ImageSequenceClip(frames, fps=fps)
        clip = clip.set_audio(AudioFileClip(audio_file))

        clip.write_videofile(
            output_video,
            codec="libvpx-vp9",
            fps=fps,
            preset="ultrafast",
            ffmpeg_params=["-pix_fmt", "yuva420p"]
        )

    # ======================
    # FRAME BUILD
    # ======================

    def _compose_frame(self, character, word):

        char_cfg = self.characters[character]

        asset_root = self.conf["asset_path"]

        body_cfg = char_cfg["sprites"]["body"]["main"]
        mouth_cfg = char_cfg["sprites"]["mouth"]["main"]

        body_dir = os.path.join(asset_root, body_cfg["path"])
        mouth_dir = os.path.join(asset_root, mouth_cfg["path"])

        body_file = sorted(os.listdir(body_dir))[0]
        body_path = os.path.join(body_dir, body_file)

        mouth_file = self._select_mouth_shape(mouth_dir, word)
        mouth_path = os.path.join(mouth_dir, mouth_file)

        body = Image.open(body_path).convert("RGBA")
        mouth = Image.open(mouth_path).convert("RGBA")

        x, y = body_cfg["mouth_pos"]

        body.paste(mouth, (x, y), mouth)

        return np.array(body)

    # ======================
    # MOUTH SELECT
    # ======================

    def _select_mouth_shape(self, mouth_dir, word):

        files = sorted(os.listdir(mouth_dir))

        vowels = "aeiou"

        for c in word.lower():
            if c in vowels:
                return files[0]   # умовно A

        return files[-1]          # умовно B
        