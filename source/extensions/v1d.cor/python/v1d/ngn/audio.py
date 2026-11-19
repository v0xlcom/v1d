# SPDX-License-Identifier: MIT
"""Clip audio: background cache, carb.audio only on transport edges."""

from __future__ import annotations

import hashlib
import os
import subprocess
import threading
from pathlib import Path


def audio_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    path = Path(base) / "v1d" / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_wav(clip: Path, dest: Path, ffmpeg: str = "ffmpeg") -> bool:
    """Spawn ffmpeg (not linked). False if there is no audio stream or the extract fails."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part.wav")
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(clip),
                "-map",
                "0:a:0",
                "-vn",
                "-c:a",
                "pcm_s16le",
                str(tmp),
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        tmp.unlink(missing_ok=True)
        return False
    if not tmp.is_file() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(dest)
    return True


class _CarbPlayer:
    """Kit playback. Imported only when a cache file is actually played."""

    def __init__(self) -> None:
        import carb.audio

        self._audio = carb.audio
        self._data = carb.audio.acquire_data_interface()
        self._playback = carb.audio.acquire_playback_interface()
        self._context = None
        self._sound = None
        self._voice = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._pump, name="v1d-audio", daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        while not self._stop.wait(0.02):
            ctx = self._context
            if ctx is not None:
                ctx.update()

    def play(self, wav: Path, seconds: float) -> None:
        if self._context is None:
            self._context = self._playback.create_context()
        if self._voice is not None:
            self._voice.stop()
            self._voice = None
        self._sound = self._data.create_sound_from_file(str(wav), streaming=True)
        ms = max(0, int(seconds * 1000))
        self._voice = self._context.play_sound(
            self._sound,
            play_start=ms,
            play_units=self._audio.UnitType.MILLISECONDS,
        )

    def pause(self) -> None:
        if self._voice is not None:
            self._voice.stop()
            self._voice = None

    def close(self) -> None:
        self.pause()
        self._sound = None
        self._context = None
        self._stop.set()


class AudioController:
    """Edge-only. open() returns immediately. play/pause never touch the video path."""

    def __init__(self, player=None, ffmpeg: str = "ffmpeg") -> None:
        self._player = player
        self._ffmpeg = ffmpeg
        self._lock = threading.Lock()
        self._gen = 0
        self._wav: Path | None = None
        self._ready = False
        self._playing = False
        self._seconds = 0.0
        self._owns_player = player is None

    def open(self, clip: str) -> None:
        self.close()
        path = Path(clip)
        key = hashlib.sha256(f"{path.resolve()}:{path.stat().st_mtime_ns}".encode()).hexdigest()[:16]
        dest = audio_cache_dir() / f"{key}.wav"
        with self._lock:
            self._gen += 1
            gen = self._gen
            self._wav = None
            self._ready = dest.is_file()
            if self._ready:
                self._wav = dest
        if dest.is_file():
            return

        def work() -> None:
            try:
                ok = extract_wav(path, dest, self._ffmpeg)
            except (OSError, subprocess.CalledProcessError):
                return
            if not ok:
                return
            with self._lock:
                if gen != self._gen:
                    return
                self._wav = dest
                self._ready = True
                playing = self._playing
                seconds = self._seconds
            if playing:
                self._start(dest, seconds)

        threading.Thread(target=work, name="v1d-audio-cache", daemon=True).start()

    def play_at(self, seconds: float) -> None:
        with self._lock:
            self._playing = True
            self._seconds = seconds
            wav = self._wav if self._ready else None
        if wav is not None:
            self._start(wav, seconds)

    def pause(self) -> None:
        with self._lock:
            self._playing = False
        if self._player is not None:
            self._player.pause()

    def close(self) -> None:
        with self._lock:
            self._gen += 1
            self._playing = False
            self._ready = False
            self._wav = None
        if self._player is not None:
            if self._owns_player:
                self._player.close()
                self._player = None
            else:
                self._player.pause()

    def _start(self, wav: Path, seconds: float) -> None:
        if self._player is None:
            self._player = _CarbPlayer()
            self._owns_player = True
        self._player.play(wav, seconds)
