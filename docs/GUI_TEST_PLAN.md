# GUI manual test plan

Run **after** `./repo.sh build -r`. Use this alongside headless checks in [BUILD_NOTES.md](BUILD_NOTES.md). Mark pass/fail per row.

GUI automation note, reviewed and not adopted: [_archive/GUI_TOOLS_RECOMMENDATION.md](../_archive/GUI_TOOLS_RECOMMENDATION.md). Control stays `tools/v1d` per [_archive/PLAN_02_MCP.md](../_archive/PLAN_02_MCP.md).

**Launch (default clip):**

```bash
./scripts/launch-v1d-terminal.sh
```

Or with an explicit clip:

```bash
ROOT=_build/linux-x86_64/release
$ROOT/kit/kit source/apps/v1d.app.kit \
  --ext-folder $ROOT/exts --ext-folder $ROOT/extscache --portable-root $ROOT \
  --/exts/v1d.cor/clip=$PWD/tests/fixtures/h264_1080_gop2.mp4
```

Keep **Preview** and **Timeline** visible (**v1d → Window**). Watch the Timeline **status** line (`tier=`, `lat=`, optional `proxy N/M`). Optional: **Upscaler** window ([PLAN_04_UPS.md](../source/extensions/v1d.ups/PLAN_04_UPS.md)).

## Headless ↔ GUI map

| Headless | GUI equivalent |
|----------|----------------|
| `./tools/run_tests.sh` (C3–C9, proxy unit tests) | Not duplicated visually; GUI confirms wiring + preview path |
| `./tools/run_kit_selftest.sh` (C10) | Same engine path; manual scrub below |
| `V1D_C11_ALL=1` … `test_proxy_c11_all.py` | Open each fixture (dropdown or path); confirm `proxy` counts then ready |
| `V1D_C12_4K=1` … `test_proxy_c12_4k.py` | **4K GOP 250** fixture: drag slider while scrubbing; `tier=proxy`, low `lat` |
| `./tools/v1d open|scrub|play|status` (C13) | Parallel **headless** API only — optional second terminal, not the Kit UI |
| `tools/s4_reverse_bench.py` / S4 table | Hold **←** / **→** on Timeline; compare feel to [SPIKES.md](SPIKES.md) S4 |

## 1. Smoke (≈5 min)

| # | Action | Pass if |
|---|--------|---------|
| 1.1 | Launch with default script | Kit starts; no modal errors; Preview shows video |
| 1.2 | **v1d → Window** | Preview and Timeline toggle show/hide; state matches menu checkmarks |
| 1.3 | Menu **Reload** | New Kit instance starts; old session exits cleanly (no hang) |

## 2. Open clip (C3 / S4 dropdown)

| # | Action | Pass if |
|---|--------|---------|
| 2.1 | Timeline **Open** with `tests/fixtures/h264_1080_gop2.mp4` | Slider range matches clip length; first frame visible |
| 2.2 | S4 combo: **Intra**, **GOP 2**, **GOP 30**, **4K GOP 250** | Each switch loads without restarting Kit; preview updates |
| 2.3 | Invalid path in **Open** | Status shows error text; app stays up |

## 3. Scrub & tier (Phase 1 + 2)

| # | Action | Pass if |
|---|--------|---------|
| 3.1 | Drag the **ruler** slowly on **GOP 2** | Preview tracks; status `tier=exact` after release |
| 3.2 | Drag the **ruler** rapidly on **GOP 2** | No crash; image keeps updating; may show `snap` while dragging |
| 3.3 | Release ruler drag; wait ~1 s | Settles to `tier=exact` on a stable frame |
| 3.4 | **4K GOP 250**: open, wait for proxy build | Status shows `proxy i/j` then scrubbing shows `tier=proxy` |
| 3.5 | Stop scrubbing on 4K | Eventually `tier=exact` on held frame |

## 4. Transport (arrows / playback)

| # | Action | Pass if |
|---|--------|---------|
| 4.1 | Tap **→** once, then tap **←** once on **GOP 2** | ±1 index; no `play▶`/`play◀` on tap; `tier=exact` after each release |
| 4.2 | Hold **→** ~2 s on **GOP 2** | ~60 frames @ 30/1; `play▶` while moving; `tier=proxy` or `snap`; release → `exact` |
| 4.3 | Hold **←** ~2 s on **GOP 2** | ~60 frames back; `play◀`; same tier behavior |
| 4.4 | **4K GOP 250** after proxy ready | Tap/hold use proxy path; not multi-second exact per step |

## 5. Upscaler (`v1d.ups`)

| # | Action | Pass if |
|---|--------|---------|
| 5.1 | **v1d → Window → Upscaler** | Six engine labels; status idle without clip |
| 5.2 | Open **GOP 2** fixture; wait for Preview frame | **Upscale frame** shows wipe; drag bar reveals original vs upscaled |
| 5.3 | Scrub Preview while Upscaler open | Preview still updates; new upscale uses latest frame |

Requires `../v1d_ups/bin/upscale-frame` (fake or ncnn). Setting: `/exts/v1d.ups/root`.

## 6. Timeline ruler & transport ([_archive/PLAN_05_TL_GUI.md](../_archive/PLAN_05_TL_GUI.md))

| # | Action | Pass if |
|---|--------|---------|
| 6.1 | Open **GOP 2** | Ruler shows full clip (Fit). Playhead at 0. No frame `IntSlider`. |
| 6.2 | **Zoom +** twice, then **Fit** | Zoom keeps playhead pixel; Fit shows whole clip again. |
| 6.3 | Zoom in; drag **overview viewport** body | Ruler scrolls; frame index unchanged until ruler drag. |
| 6.4 | Drag ruler, release | Preview tracks; `tier=proxy` or `snap` while dragging; `tier=exact` after release. |
| 6.5 | **−1** then **+1** | ±1 frame; `tier=exact`; no `play▶`/`play◀` on those taps. |
| 6.6 | **Play** ~2 s, **Stop** | ~60 frames @ 30/1; `play▶` while running; stop → `exact`; playhead in view. |
| 6.7 | **Reverse** ~2 s, **Stop** | Same backward; `play◀`. |
| 6.8 | **Start** and **End** | Frame 0 and last frame; `tier=exact`. |

## 7. Lens strip, viewport, and wheel ([PLAN_06_GUI_UPDATE.md](../_archive/PLAN_06_GUI_UPDATE.md))

| # | Action | Pass if |
|---|--------|---------|
| 7.1 | Open **GOP 30**, Fit | Cyan viewport spans the strip; lens trapezoid; clock `00h:00m:00s:00f`; zoom reads 100%. Detail grid stays hidden. A magenta V on the Frames ruler points at the 1 px magenta line over the tracks. Drag the V; the line and the preview follow, and they stay put on release. |
| 7.2 | Zoom to **5%** (30 frames of 600) | Detail shows even 1 px white gaps and dark bodies; magenta playhead is the gap of the current frame. |
| 7.3 | Drag the cyan bar | The playhead stays on its frame, including outside the bar. Frame index unchanged. |
| 7.4 | Drag viewport **right** edge inward | Zooms in; left edge frame fixed. |
| 7.5 | **Fit** | Viewport spans full strip again. |
| 7.6 | Click **clip block** (top track) | Seeks that frame; preview updates. |
| 7.7 | Wheel up/down over **detail** (several notches each way) | **5%** steps (100, 95, 90, … down to one second, which is **5%** on GOP 30). Not one step only, and not ×2 / ×0.5 (those are **Zoom + / −**). The frame under the cursor stays at the **horizontal center** of the strip. Playhead index unchanged. Contract: [UI_EXTENSIONS.md](UI_EXTENSIONS.md). |
| 7.8 | Quit Kit | No long freeze tearing down timeline (no per-frame widget pool). |
| 7.9 | **Play** from 0 | Playhead runs across the cyan bar, then the bar jumps and the line sits on the bar’s left edge. It does not stay glued to the right edge. |
| 7.10 | Let **Play** finish | Reaches frame 599 (`00h:00m:19s:29f`), not 598. |
| 7.11 | Zoom out until frames are thinner than 1 px | Frame rectangles disappear. The frame-track playhead stays a 1 px magenta line. |

## 8. Clip block and second track ([PLAN_CLIP_N_2_TRACK.md](../PLAN_CLIP_N_2_TRACK.md))

| # | Action | Pass if |
|---|--------|---------|
| 8.1 | Open **GOP 2** | Two detail rows; **both** show the frame grid when zoomed in; blue clip blocks about half the ruler; zoom stays fixed while dragging a block. |
| 8.2 | Click inside top clip | Seeks; preview updates; no decode while dragging the clip body. |
| 8.3 | Drag clip body right ~30 frames | Block moves; preview unchanged until release; after click inside, frame matches playhead under the block. |
| 8.4 | Drag either light end bar and release on a frame number | Pointer is a left-right arrow on the bar. That edge sits on the number under the pointer; the other edge stays. At least one frame remains. Dragging back out restores frames still in the file. The picture updates after release. |
| 8.5 | Select bottom track, click its clip | Preview follows the selected track; same file, no second open dialog. |

## 12. Two-track play ([PLAN_TWO_TRACKS.md](../PLAN_TWO_TRACKS.md))

| # | Action | Pass if |
|---|--------|---------|
| 12.1 | Trim T1 to ~frame 226; T2 full; Play from 0 | Playhead and preview continue on T2 after 226; stop at end of T2 span. |
| 12.2 | Reverse play from beyond 226 | Playhead reaches span start; preview follows. |
| 12.3 | Hold → across 226 | Shuttle passes T1 end without stopping. |
| 12.4 | Tap → at 226 | Single step lands on 227 with T2 picture. |
| 12.5 | Move T2 right leaving a gap; Play through it | Playhead advances; preview blank in gap; picture returns on T2. |
| 12.6 | Start Play inside empty span | Playhead moves; preview blank until next block. |
| 12.7 | T2 video off (eye) | Play stops at T1 end. |

## 14. Add / delete tracks ([PLAN_MULTITRACK.md](../PLAN_MULTITRACK.md))

| # | Action | Pass if |
|---|--------|---------|
| 14.1 | Right-click empty space on T1, or right-click the **track header** (T1 label, eye, speaker, or header padding) | Menu shows **Add Track** and **Delete Track**. |
| 14.2 | Right-click a clip body | No menu. |
| 14.3 | **Add Track** after right-click **lower half** of T1 | New empty row inserted **below** T1; labels renumber; new row selected. |
| 14.3b | **Add Track** after right-click **upper half** of T2 (track header or strip) | New empty row inserted **above** T2 (between T1 and T2). |
| 14.4 | **Delete Track** on a row with a clip | Row and clip gone; others renumber; preview/span update. |
| 14.5 | One track left | **Delete Track** greyed out. |
| 14.6 | Eight tracks | **Add Track** greyed out. |
| 14.7 | Start Play, right-click empty row | Transport stops before the menu opens. |
| 14.8 | Add a track, quit Kit, reopen same clip | Same track count as before quit. |

## 13. Block move across tracks ([PLAN_BLOCK_MOVE.md](../PLAN_BLOCK_MOVE.md))

| # | Action | Pass if |
|---|--------|---------|
| 13.1 | Trim T1 and T2 so each block is shorter than half the strip; place T2 block on a free span | Both blocks visible on their rows. |
| 13.2 | Press Play, then drag a clip body | Transport stops before the drag starts. |
| 13.3 | Drag T1 block over T2 on a clear span | Source block dims at original start; T2 row highlights; cyan ghost follows pointer on T2. |
| 13.4 | Release on the ghost position | Block on T2 at that frame; T2 selected; preview matches; `in`/`out` unchanged. |
| 13.5 | Drag onto T2 where blocks overlap but a shorter gap fits | Amber ghost shows nudged frame; status `Nudged to frame N on T2`; block lands there. |
| 13.6 | Drag onto T2 with no gap large enough | Block back on T1 at press position; status `No room on T2`. |
| 13.7 | Drag off the strip and release | Block restored; status `Move cancelled`. |
| 13.8 | Same-row drag into neighbour | Block stops at neighbour (no jump past). |
| 13.9 | Two blocks on T1 (duplicate track or add second clip via future UI) | Both drawn; click/trim on each; trim stops at the other block. |

## 11. Track column ([PLAN_TRACK_COLUMN.md](../PLAN_TRACK_COLUMN.md))

| # | Action | Pass if |
|---|--------|---------|
| 11.1 | Open GOP 2 | Column cell sits left of the overview, the cyan lens, the ruler, and both tracks. Those four sections share one left edge. The overview thumb still grows and shrinks with zoom. T1 on the top row, T2 on the bottom. |
| 11.2 | Click eye on T1 | Icon flips; that clip dims; preview leaves that track. Speaker does not change the picture. |
| 11.3 | Click speaker on T2 | Icon flips; preview unchanged. |
| 11.4 | Drag the T1 title onto the T2 row | Rows swap; labels follow; selection stays on the same track. |
| 11.5 | Drag a clip body onto the other track | Block moves to that row. Trim-edge drag stays on the original track. |
| 11.6 | Zoom + then Fit, drag a clip on the same track | Zoom and same-track drag feel unchanged. |

## 9. Visual sanity (optional, barcode fixtures)

On **GOP 2** or **Intra**, jump to frame 0, mid, last via ruler drag: colored barcode blocks look sharp (no torn RGB, no stale frame from a different index). No need to verify bits by eye if headless C4 already passed.

## 10. Automated GUI gate (when tired of clicking)

```bash
./tools/run_kit_selftest.sh
```

Use this to re-check C10; keep sections 1–2 manual at least once per release.

## 15. Import video ([PLAN_DRAG-DROP_RENDER_SAVE.md](../PLAN_DRAG-DROP_RENDER_SAVE.md))

| # | Action | Pass if |
|---|--------|---------|
| 15.1 | **File → Add Video…** on empty T2 | Clip lands on selected row; preview shows it. |
| 15.2 | Drag MP4 from Nemo onto timeline strip | Same as add (if drop works); else use Add Video. |
| 15.3 | Drop MKV | Rejected; status mentions unsupported container. |

## 16. Scissor / timestretch ([PLAN_DRAG-DROP_RENDER_SAVE.md](../PLAN_DRAG-DROP_RENDER_SAVE.md))

| # | Action | Pass if |
|---|--------|---------|
| 16.1 | Playhead mid-clip, scissor | Two blocks; preview unchanged frame. |
| 16.2 | Clock on (cyan), drag right edge wider | Label shows ×speed; slower motion (repeated frames). |
| 16.3 | Clock off, edge drag | Trim behaves as before. |

## 17. Save / New / Open `.v1d`

| # | Action | Pass if |
|---|--------|---------|
| 17.1 | Move a clip, **Save .v1d**, **New .v1d**, **Open .v1d** | Composition restored; media paths resolve. |
| 17.2 | **New** with dirty project | Save / Discard / Cancel dialog. |

## 18. Render window

| # | Action | Pass if |
|---|--------|---------|
| 18.1 | **File → Render…** | Render window opens. |
| 18.2 | Render short span to `~/Videos` | MP4 written; plays in mpv. |

## Notes

- **Logs:** `~/.local/share/v1d/v1d.log` (launch script) or `_build/.../logs/Kit/v1d.app/`.
- **GPU required** for meaningful scrub/proxy behavior.
- Bad-input clips (truncated MP4, etc.) are headless-only (C9); GUI test is invalid-path only.
