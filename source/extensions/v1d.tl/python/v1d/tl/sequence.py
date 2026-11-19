# SPDX-License-Identifier: MIT
"""Timeline sequence model (tracks, clips). No Kit or engine I/O."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Literal

import pathlib

MoveReason = Literal["ok", "same_track", "bad_index", "no_room", "missing_clip"]
CutReason = Literal["ok", "no_clip", "at_start", "bad_index"]
AddReason = Literal["ok", "bad_index", "no_room", "bad_frames"]

SPEED_MIN = 0.25
SPEED_MAX = 4.0


def _new_clip_id() -> str:
    return uuid.uuid4().hex


def _clamp_speed(speed: float) -> float:
    return max(SPEED_MIN, min(SPEED_MAX, float(speed)))


# Sequence ruler is longer than the media so clips are not full-width (edit headroom).
TIMELINE_DURATION_SCALE = 2
MAX_TRACKS = 8


@dataclass
class Clip:
    id: str
    media_path: str
    start_frame: int
    in_frame: int
    out_frame: int
    speed: float = 1.0

    @property
    def source_frame_count(self) -> int:
        return self.out_frame - self.in_frame + 1

    @property
    def duration(self) -> int:
        return max(1, round(self.source_frame_count / self.speed))

    @property
    def end_frame(self) -> int:
        return self.start_frame + self.duration - 1

    def contains_sequence(self, playhead: int) -> bool:
        return self.start_frame <= int(playhead) <= self.end_frame

    def source_at(self, playhead: int) -> int | None:
        if not self.contains_sequence(playhead):
            return None
        return self.in_frame + math.floor((int(playhead) - self.start_frame) * self.speed)

    def sequence_at_source(self, source: int) -> int | None:
        src = int(source)
        if src < self.in_frame or src > self.out_frame:
            return None
        return self.start_frame + math.floor((src - self.in_frame) / self.speed)


@dataclass
class Track:
    id: str
    index: int
    clips: list[Clip] = field(default_factory=list)
    video_enabled: bool = True
    audio_enabled: bool = True

    def clip_by_id(self, clip_id: str) -> Clip | None:
        for clip in self.clips:
            if clip.id == clip_id:
                return clip
        return None

    def clip_at_sequence(self, playhead: int) -> Clip | None:
        for clip in self.clips:
            if clip.contains_sequence(playhead):
                return clip
        return None

    def _sorted_clips(self) -> list[Clip]:
        return sorted(self.clips, key=lambda c: c.start_frame)

    def _would_overlap(self, candidate: Clip, ignore_id: str | None = None) -> bool:
        c0 = candidate.start_frame
        c1 = candidate.end_frame
        for other in self.clips:
            if ignore_id is not None and other.id == ignore_id:
                continue
            o0 = other.start_frame
            o1 = other.end_frame
            if c0 <= o1 and c1 >= o0:
                return True
        return False


@dataclass
class Sequence:
    playhead: int = 0
    media_frame_count: int = 0
    timeline_frame_count: int = 0
    media_path: str = ""
    selected_track: int = 0
    fps_num: int = 30
    fps_den: int = 1
    tracks: list[Track] = field(default_factory=list)
    _dirty_generation: int = field(default=0, repr=False)

    @property
    def dirty_generation(self) -> int:
        return self._dirty_generation

    def _bump_dirty(self) -> None:
        self._dirty_generation += 1

    def mark_clean(self) -> None:
        self._dirty_generation = 0

    @classmethod
    def empty(cls, track_count: int = 2, timeline_frame_count: int = 600) -> Sequence:
        want = max(1, min(MAX_TRACKS, int(track_count)))
        tracks = [Track(id=_new_clip_id(), index=i, clips=[]) for i in range(want)]
        return cls(
            playhead=0,
            media_frame_count=0,
            timeline_frame_count=max(1, int(timeline_frame_count)),
            media_path="",
            selected_track=0,
            tracks=tracks,
        )

    @classmethod
    def from_opened_media(
        cls,
        media_path: str,
        frame_count: int,
        duration_scale: int = TIMELINE_DURATION_SCALE,
        track_count: int = 2,
    ) -> Sequence:
        n = max(0, int(frame_count))
        scale = max(1, int(duration_scale))
        timeline_n = n * scale if n > 0 else 0
        fm = max(0, n - 1)
        clip = Clip(
            id=_new_clip_id(),
            media_path=media_path,
            start_frame=0,
            in_frame=0,
            out_frame=fm,
        )
        t0 = Track(id=_new_clip_id(), index=0, clips=[clip])
        seq = cls(
            playhead=0,
            media_frame_count=n,
            timeline_frame_count=timeline_n,
            media_path=media_path,
            selected_track=0,
            tracks=[t0],
        )
        want = max(1, min(MAX_TRACKS, int(track_count)))
        if want >= 2:
            seq.duplicate_track()
        while len(seq.tracks) < want:
            seq.tracks.append(Track(id=_new_clip_id(), index=len(seq.tracks), clips=[]))
        for i, track in enumerate(seq.tracks):
            track.index = i
        return seq

    @property
    def sequence_frame_max(self) -> int:
        return max(0, self.timeline_frame_count - 1)

    def selected_track_model(self) -> Track | None:
        if not self.tracks:
            return None
        idx = max(0, min(len(self.tracks) - 1, int(self.selected_track)))
        return self.tracks[idx]

    def source_for_selected(self, playhead: int | None = None) -> int | None:
        track = self.selected_track_model()
        if track is None:
            return None
        ph = int(playhead if playhead is not None else self.playhead)
        clip = track.clip_at_sequence(ph)
        if clip is None:
            return None
        return clip.source_at(ph)

    def preview_clip(self, playhead: int | None = None) -> Clip | None:
        if not self.tracks:
            return None
        ph = int(playhead if playhead is not None else self.playhead)
        sel_idx = max(0, min(len(self.tracks) - 1, int(self.selected_track)))
        sel = self.tracks[sel_idx]
        if sel.video_enabled:
            clip = sel.clip_at_sequence(ph)
            if clip is not None:
                return clip
        for i, track in enumerate(self.tracks):
            if i == sel_idx:
                continue
            if not track.video_enabled:
                continue
            clip = track.clip_at_sequence(ph)
            if clip is not None:
                return clip
        return None

    def sequence_playback_span(self) -> tuple[int, int] | None:
        """Union of sequence frames covered by video-enabled tracks."""
        lo: int | None = None
        hi: int | None = None
        for track in self.tracks:
            if not track.video_enabled:
                continue
            for clip in track.clips:
                if lo is None:
                    lo = clip.start_frame
                    hi = clip.end_frame
                else:
                    lo = min(lo, clip.start_frame)
                    hi = max(hi, clip.end_frame)
        if lo is None:
            return None
        return max(0, lo), min(self.sequence_frame_max, hi)

    def preview_source(self, playhead: int | None = None) -> int | None:
        clip = self.preview_clip(playhead)
        if clip is None:
            return None
        ph = int(playhead if playhead is not None else self.playhead)
        return clip.source_at(ph)

    def move_track(self, index: int, new_index: int) -> bool:
        n = len(self.tracks)
        if index < 0 or index >= n:
            return False
        if index == new_index:
            return True
        new_index = max(0, min(n - 1, int(new_index)))
        if index == new_index:
            return True
        sel = self.selected_track_model()
        sel_id = sel.id if sel is not None else None
        track = self.tracks.pop(index)
        self.tracks.insert(new_index, track)
        for i, t in enumerate(self.tracks):
            t.index = i
        if sel_id is not None:
            for i, t in enumerate(self.tracks):
                if t.id == sel_id:
                    self.selected_track = i
                    break
        self._bump_dirty()
        return True

    def free_start_on_track(
        self,
        track_index: int,
        duration: int,
        want_start: int,
        ignore_id: str | None = None,
    ) -> int | None:
        if track_index < 0 or track_index >= len(self.tracks) or duration < 1:
            return None
        track = self.tracks[track_index]
        dur = int(duration)
        max_start = max(0, self.sequence_frame_max - dur + 1)
        want = max(0, min(max_start, int(want_start)))

        def fits(start: int) -> bool:
            end = start + dur - 1
            for other in track.clips:
                if ignore_id is not None and other.id == ignore_id:
                    continue
                if start <= other.end_frame and end >= other.start_frame:
                    return False
            return True

        if fits(want):
            return want
        candidates: list[int] = []
        for other in track._sorted_clips():
            if ignore_id is not None and other.id == ignore_id:
                continue
            gap_after = other.end_frame + 1
            if gap_after <= max_start and fits(gap_after):
                candidates.append(gap_after)
            gap_before = other.start_frame - dur
            if 0 <= gap_before <= max_start and fits(gap_before):
                candidates.append(gap_before)
        for edge in (0, max_start):
            if fits(edge):
                candidates.append(edge)
        if not candidates:
            return None
        best = min(candidates, key=lambda s: (abs(s - want), s))
        return best

    def move_clip(self, clip_id: str, dest_index: int, want_start: int) -> tuple[MoveReason, int | None]:
        if dest_index < 0 or dest_index >= len(self.tracks):
            return ("bad_index", None)
        src_index: int | None = None
        clip: Clip | None = None
        for ti, track in enumerate(self.tracks):
            found = track.clip_by_id(clip_id)
            if found is not None:
                src_index = ti
                clip = found
                break
        if clip is None or src_index is None:
            return ("missing_clip", None)
        start = self.free_start_on_track(dest_index, clip.duration, want_start, ignore_id=clip.id)
        if start is None:
            return ("no_room", None)
        if src_index == dest_index:
            if start == clip.start_frame:
                return ("same_track", start)
            if not self.set_clip_start(dest_index, clip_id, start):
                return ("no_room", None)
            return ("ok", start)
        self.tracks[src_index].clips.remove(clip)
        clip.start_frame = start
        self.tracks[dest_index].clips.append(clip)
        self.selected_track = dest_index
        self._bump_dirty()
        return ("ok", start)

    def move_clip_to_track(self, clip_id: str, dest_index: int) -> bool:
        src_index: int | None = None
        clip: Clip | None = None
        for ti, track in enumerate(self.tracks):
            found = track.clip_by_id(clip_id)
            if found is not None:
                src_index = ti
                clip = found
                break
        if clip is None or src_index is None:
            return False
        reason, _ = self.move_clip(clip_id, dest_index, clip.start_frame)
        return reason in ("ok", "same_track")

    def restore_clip_geometry(self, track_index: int, clip_id: str, snap: Clip) -> None:
        clip = self.tracks[track_index].clip_by_id(clip_id)
        if clip is None:
            return
        clip.start_frame = snap.start_frame
        clip.in_frame = snap.in_frame
        clip.out_frame = snap.out_frame
        clip.speed = snap.speed
        self._bump_dirty()

    def set_playhead_from_source(self, track_index: int, source: int) -> int | None:
        if track_index < 0 or track_index >= len(self.tracks):
            return None
        track = self.tracks[track_index]
        for clip in track.clips:
            seq = clip.sequence_at_source(source)
            if seq is not None:
                self.playhead = seq
                return seq
        return None

    def duplicate_track(self) -> Track:
        if not self.tracks:
            raise RuntimeError("no tracks")
        src = self.tracks[-1]
        copies: list[Clip] = []
        for clip in src.clips:
            copies.append(
                Clip(
                    id=_new_clip_id(),
                    media_path=clip.media_path,
                    start_frame=clip.start_frame,
                    in_frame=clip.in_frame,
                    out_frame=clip.out_frame,
                    speed=clip.speed,
                )
            )
        track = Track(id=_new_clip_id(), index=len(self.tracks), clips=copies)
        self.tracks.append(track)
        self._bump_dirty()
        return track

    def add_track(self, anchor_index: int, *, above: bool = False) -> Track | None:
        if len(self.tracks) >= MAX_TRACKS:
            return None
        if anchor_index < 0 or anchor_index >= len(self.tracks):
            return None
        ins = anchor_index if above else anchor_index + 1
        track = Track(id=_new_clip_id(), index=ins, clips=[])
        self.tracks.insert(ins, track)
        for i, t in enumerate(self.tracks):
            t.index = i
        self.selected_track = ins
        self._bump_dirty()
        return track

    def delete_track(self, index: int) -> bool:
        if len(self.tracks) <= 1:
            return False
        if index < 0 or index >= len(self.tracks):
            return False
        sel = self.selected_track_model()
        sel_id = sel.id if sel is not None else None
        self.tracks.pop(index)
        for i, t in enumerate(self.tracks):
            t.index = i
        self._bump_dirty()
        if sel_id is not None:
            for i, t in enumerate(self.tracks):
                if t.id == sel_id:
                    self.selected_track = i
                    return True
        self.selected_track = min(index, len(self.tracks) - 1)
        return True

    def set_clip_start(self, track_index: int, clip_id: str, start_frame: int) -> bool:
        track = self.tracks[track_index]
        clip = track.clip_by_id(clip_id)
        if clip is None:
            return False
        return self.move_clip_body(track_index, clip_id, int(start_frame) - clip.start_frame)

    def restore_and_trim_left(self, track_index: int, clip_id: str, base: Clip, total_delta: int) -> bool:
        track = self.tracks[track_index]
        clip = track.clip_by_id(clip_id)
        if clip is None:
            return False
        clip.start_frame = base.start_frame
        clip.in_frame = base.in_frame
        clip.out_frame = base.out_frame
        clip.speed = base.speed
        return self.trim_left(track_index, clip_id, int(total_delta))

    def restore_and_trim_right(self, track_index: int, clip_id: str, base: Clip, total_delta: int) -> bool:
        track = self.tracks[track_index]
        clip = track.clip_by_id(clip_id)
        if clip is None:
            return False
        clip.start_frame = base.start_frame
        clip.in_frame = base.in_frame
        clip.out_frame = base.out_frame
        clip.speed = base.speed
        return self.trim_right(track_index, clip_id, int(total_delta))

    def cut_at(self, track_index: int, frame: int) -> tuple[CutReason, str | None]:
        if track_index < 0 or track_index >= len(self.tracks):
            return ("bad_index", None)
        track = self.tracks[track_index]
        at = int(frame)
        clip = track.clip_at_sequence(at)
        if clip is None:
            return ("no_clip", None)
        if at <= clip.start_frame:
            return ("at_start", None)
        left_out = clip.source_at(at - 1)
        right_in = clip.source_at(at)
        if left_out is None or right_in is None:
            return ("at_start", None)
        orig_out = clip.out_frame
        clip.out_frame = left_out
        new_id = _new_clip_id()
        track.clips.append(
            Clip(
                id=new_id,
                media_path=clip.media_path,
                start_frame=at,
                in_frame=right_in,
                out_frame=orig_out,
                speed=clip.speed,
            )
        )
        self._bump_dirty()
        return ("ok", new_id)

    def set_clip_speed_edge(
        self,
        track_index: int,
        clip_id: str,
        base: Clip,
        edge: Literal["left", "right"],
        frame_at_pointer: int,
    ) -> bool:
        track = self.tracks[track_index]
        clip = track.clip_by_id(clip_id)
        if clip is None:
            return False
        clip.start_frame = base.start_frame
        clip.in_frame = base.in_frame
        clip.out_frame = base.out_frame
        clip.speed = base.speed
        src_n = base.source_frame_count
        f = int(frame_at_pointer)
        if edge == "right":
            new_end = max(base.start_frame, f - 1)
            new_len = max(1, new_end - base.start_frame + 1)
            speed = _clamp_speed(src_n / new_len)
            new_len = max(1, round(src_n / speed))
            new_end = base.start_frame + new_len - 1
            max_end = self.sequence_frame_max
            for other in track.clips:
                if other.id == clip_id or other.start_frame <= base.end_frame:
                    continue
                max_end = min(max_end, other.start_frame - 1)
            new_end = min(new_end, max_end)
            new_len = max(1, new_end - base.start_frame + 1)
            speed = _clamp_speed(src_n / new_len)
            trial = Clip(clip_id, base.media_path, base.start_frame, base.in_frame, base.out_frame, speed)
            if track._would_overlap(trial, ignore_id=clip_id):
                return False
            clip.speed = speed
        else:
            new_start = min(f, base.end_frame)
            new_len = max(1, base.end_frame - new_start + 1)
            speed = _clamp_speed(src_n / new_len)
            new_len = max(1, round(src_n / speed))
            new_start = base.end_frame - new_len + 1
            min_start = 0
            for other in track.clips:
                if other.id == clip_id or other.end_frame >= base.start_frame:
                    continue
                min_start = max(min_start, other.end_frame + 1)
            new_start = max(new_start, min_start)
            new_len = max(1, base.end_frame - new_start + 1)
            speed = _clamp_speed(src_n / new_len)
            trial = Clip(clip_id, base.media_path, new_start, base.in_frame, base.out_frame, speed)
            if track._would_overlap(trial, ignore_id=clip_id):
                return False
            clip.start_frame = new_start
            clip.speed = speed
        self._bump_dirty()
        return True

    def add_clip(
        self,
        track_index: int,
        media_path: str,
        source_frame_count: int,
        want_start: int,
        extend: bool = False,
    ) -> tuple[AddReason, Clip | None]:
        """Add a clip near ``want_start``. With ``extend``, a clip that finds no gap
        is appended after the track's last clip; the timeline grows to hold it."""
        if track_index < 0 or track_index >= len(self.tracks):
            return ("bad_index", None)
        n = int(source_frame_count)
        if n < 1:
            return ("bad_frames", None)
        fm = n - 1
        duration = max(1, round(n / 1.0))
        start = self.free_start_on_track(track_index, duration, want_start)
        if start is None and extend:
            last_end = max((c.end_frame for c in self.tracks[track_index].clips), default=-1)
            start = last_end + 1
        if start is None:
            return ("no_room", None)
        clip = Clip(
            id=_new_clip_id(),
            media_path=media_path,
            start_frame=start,
            in_frame=0,
            out_frame=fm,
        )
        self.tracks[track_index].clips.append(clip)
        end = clip.end_frame
        need = (end + 1) * TIMELINE_DURATION_SCALE
        if need > self.timeline_frame_count:
            self.timeline_frame_count = need
        if self.media_frame_count < n:
            self.media_frame_count = n
        self._bump_dirty()
        return ("ok", clip)

    def _clip_to_dict(self, clip: Clip, base_dir: pathlib.Path | None) -> dict:
        path = pathlib.Path(clip.media_path)
        rel = ""
        if base_dir is not None:
            try:
                rel = str(path.relative_to(base_dir))
            except ValueError:
                rel = ""
        media_size = 0
        media_mtime = 0
        try:
            st = path.stat()
            media_size = int(st.st_size)
            media_mtime = int(st.st_mtime)
        except OSError:
            pass
        return {
            "id": clip.id,
            "media": str(path.resolve()) if path.is_absolute() else clip.media_path,
            "media_rel": rel,
            "media_size": media_size,
            "media_mtime": media_mtime,
            "start": clip.start_frame,
            "in": clip.in_frame,
            "out": clip.out_frame,
            "speed": clip.speed,
        }

    def to_dict(self, base_dir: pathlib.Path | None = None) -> dict:
        tracks_out = []
        for track in self.tracks:
            tracks_out.append(
                {
                    "video_enabled": track.video_enabled,
                    "audio_enabled": track.audio_enabled,
                    "clips": [self._clip_to_dict(c, base_dir) for c in track.clips],
                }
            )
        return {
            "format": "v1d",
            "version": 1,
            "sequence": {
                "fps_num": self.fps_num,
                "fps_den": self.fps_den,
                "timeline_frame_count": self.timeline_frame_count,
                "playhead": self.playhead,
                "selected_track": self.selected_track,
                "tracks": tracks_out,
            },
        }

    @classmethod
    def from_dict(cls, data: dict, base_dir: pathlib.Path | None = None) -> Sequence:
        if int(data.get("version", 0)) > 1:
            raise ValueError(f"unsupported .v1d version {data.get('version')}")
        if data.get("format") != "v1d":
            raise ValueError("not a v1d project")
        seq = data.get("sequence") or {}
        fps_num = int(seq.get("fps_num", 30))
        fps_den = int(seq.get("fps_den", 1))
        tracks: list[Track] = []
        for ti, td in enumerate(seq.get("tracks") or []):
            clips: list[Clip] = []
            for cd in td.get("clips") or []:
                media = str(cd.get("media") or "")
                rel = str(cd.get("media_rel") or "")
                if base_dir is not None and rel:
                    candidate = base_dir / rel
                    if candidate.is_file():
                        media = str(candidate.resolve())
                clips.append(
                    Clip(
                        id=str(cd.get("id") or _new_clip_id()),
                        media_path=media,
                        start_frame=int(cd.get("start", 0)),
                        in_frame=int(cd.get("in", 0)),
                        out_frame=int(cd.get("out", 0)),
                        speed=float(cd.get("speed", 1.0)),
                    )
                )
            tracks.append(
                Track(
                    id=_new_clip_id(),
                    index=ti,
                    clips=clips,
                    video_enabled=bool(td.get("video_enabled", True)),
                    audio_enabled=bool(td.get("audio_enabled", True)),
                )
            )
        media_n = 0
        media_path = ""
        for track in tracks:
            for clip in track.clips:
                media_n = max(media_n, clip.out_frame + 1)
                if not media_path:
                    media_path = clip.media_path
        return cls(
            playhead=int(seq.get("playhead", 0)),
            media_frame_count=media_n,
            timeline_frame_count=int(seq.get("timeline_frame_count", 0)),
            media_path=media_path,
            selected_track=int(seq.get("selected_track", 0)),
            fps_num=fps_num,
            fps_den=fps_den,
            tracks=tracks,
        )

    def move_clip_body(self, track_index: int, clip_id: str, delta: int) -> bool:
        track = self.tracks[track_index]
        clip = track.clip_by_id(clip_id)
        if clip is None or delta == 0:
            return delta == 0
        new_start = clip.start_frame + int(delta)
        max_start = self.sequence_frame_max - clip.duration + 1
        if max_start < 0:
            max_start = 0
        new_start = max(0, min(max_start, new_start))
        if new_start == clip.start_frame:
            return True
        step = -1 if new_start > clip.start_frame else 1
        trial_start = new_start
        while True:
            trial = Clip(
                id=clip.id,
                media_path=clip.media_path,
                start_frame=trial_start,
                in_frame=clip.in_frame,
                out_frame=clip.out_frame,
                speed=clip.speed,
            )
            if not track._would_overlap(trial, ignore_id=clip.id):
                clip.start_frame = trial_start
                self._bump_dirty()
                return True
            if trial_start == clip.start_frame:
                return False
            trial_start += step
            if step < 0 and trial_start < clip.start_frame:
                return False
            if step > 0 and trial_start > clip.start_frame:
                return False

    def trim_left(self, track_index: int, clip_id: str, delta: int) -> bool:
        """Positive delta moves the left edge right. The right edge stays."""
        track = self.tracks[track_index]
        clip = track.clip_by_id(clip_id)
        if clip is None:
            return False
        d = int(delta)
        max_shrink = clip.out_frame - clip.in_frame
        if d > max_shrink:
            d = max_shrink
        floor = max(-clip.in_frame, -clip.start_frame)
        if d < floor:
            d = floor
        if d < 0:
            min_start = 0
            for other in track.clips:
                if other.id == clip.id or other.end_frame >= clip.start_frame:
                    continue
                min_start = max(min_start, other.end_frame + 1)
            d = max(d, min_start - clip.start_frame)
        if d == 0:
            return True
        clip.in_frame += d
        clip.start_frame += d
        self._bump_dirty()
        return True

    def trim_right(self, track_index: int, clip_id: str, delta: int) -> bool:
        """Positive delta moves the right edge right. The left edge stays."""
        track = self.tracks[track_index]
        clip = track.clip_by_id(clip_id)
        if clip is None:
            return False
        fm = max(0, self.media_frame_count - 1)
        new_out = clip.out_frame + int(delta)
        new_out = max(clip.in_frame, min(fm, new_out))
        max_out = self.sequence_frame_max - clip.start_frame + clip.in_frame
        if max_out < clip.in_frame:
            return True
        new_out = min(new_out, max_out)
        if int(delta) > 0:
            max_end = self.sequence_frame_max
            for other in track.clips:
                if other.id == clip.id or other.start_frame <= clip.end_frame:
                    continue
                max_end = min(max_end, other.start_frame - 1)
            cap = max_end - clip.start_frame + clip.in_frame
            new_out = min(new_out, max(clip.out_frame, cap))
        if new_out == clip.out_frame:
            return True
        clip.out_frame = new_out
        self._bump_dirty()
        return True