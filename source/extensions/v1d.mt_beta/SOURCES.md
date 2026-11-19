# OpenTimelineIO sources — multitrack timeline & clip editing

Curated bibliography from [OpenTimelineIO Read the Docs](https://opentimelineio.readthedocs.io/en/stable/) (`en/stable` as of 2026-10-11). Use for **v1d.mt**: multitrack video/audio editorial structure, timing, interchange, and playback semantics. OTIO describes cuts and composition; **v1d still owns decode, GPU compositing, and real-time playback**.

Upstream doc tree (authoritative path list): [OpenTimelineIO `docs/index.rst`](https://github.com/AcademySoftwareFoundation/OpenTimelineIO/blob/main/docs/index.rst).

License for OTIO itself: [LICENSE.txt (Apache 2.0)](https://github.com/AcademySoftwareFoundation/OpenTimelineIO/blob/main/LICENSE.txt).

---

## 1. Core model — tracks, clips, stacks, rendering semantics

| Topic | URL | Why it matters for v1d.mt |
|--------|-----|---------------------------|
| **Timeline structure** (cut lists, transitions, multitrack, nesting, **Rendering**) | https://opentimelineio.readthedocs.io/en/stable/tutorials/otio-timeline-structure.html | Canonical nesting: `Timeline` → `Stack` (`tracks`) → `Track` → `Clip` / `Gap` / `Transition` / nested `Stack`/`Track`. Defines **video**: bottom-to-top alpha composite in stacks; **in-track** transition = linear blend; **audio**: additive mix. |
| **Time ranges** (clip/track/stack/timeline API) | https://opentimelineio.readthedocs.io/en/stable/tutorials/time-ranges.html | `trimmed_range`, `visible_range` (transitions), `range_in_parent`, track child indexing — needed for edit tools, playhead mapping, and conform. |
| **Architecture** (canonical structure, traversal, clip timing) | https://opentimelineio.readthedocs.io/en/stable/tutorials/architecture.html | `timeline.tracks` stack, `each_clip()`, `source_range` vs `available_range`, adapters overview. |
| **Spatial coordinates** (multitrack layouts, PiP, bounds) | https://opentimelineio.readthedocs.io/en/stable/tutorials/spatial-coordinates.html | Optional: per-clip `available_image_bounds` when multiple video layers are not full-frame; same canvas across the timeline. |

---

## 2. Schema & on-disk format

| Topic | URL | Why it matters for v1d.mt |
|--------|-----|---------------------------|
| **File format specification** (`.otio` JSON, nesting, metadata) | https://opentimelineio.readthedocs.io/en/stable/tutorials/otio-file-format-specification.html | Tree rules, `Track.kind`, example multitrack + transitions JSON. |
| **Serialized schema** (field docs: `Clip`, `Track`, `Transition`, effects) | https://opentimelineio.readthedocs.io/en/stable/tutorials/otio-serialized-schema.html | `Track.kind` (video/audio), `enabled` (mute/hide), `LinearTimeWarp` / `FreezeFrame`, multi `media_references` on clips. |
| **Serialized schema (fields only)** | https://opentimelineio.readthedocs.io/en/stable/tutorials/otio-serialized-schema-only-fields.html | Quick reference when implementing readers/writers. |
| **Versioning schemas** | https://opentimelineio.readthedocs.io/en/stable/tutorials/versioning-schemas.html | Read older `.otio`, downgrade for interchange, `OTIO_DEFAULT_TARGET_VERSION_FAMILY_LABEL`. |
| **Developing a new schema** | https://opentimelineio.readthedocs.io/en/stable/tutorials/developing-a-new-schema.html | If v1d needs custom schema or metadata promotion. |
| **SchemaDef plugins** | https://opentimelineio.readthedocs.io/en/stable/tutorials/write-a-schemadef.html | Studio-specific types without forking OTIO core. |

---

## 3. Interchange, bundles, and format coverage

| Topic | URL | Why it matters for v1d.mt |
|--------|-----|---------------------------|
| **Adapters** (built-in, plugins, EDL/AAF/FCP, etc.) | https://opentimelineio.readthedocs.io/en/stable/tutorials/adapters.html | Import/export editorial from NLEs; `.otio` is the only **lossless** OTIO container. |
| **Feature matrix** (multitrack, audio, transitions per adapter) | https://opentimelineio.readthedocs.io/en/stable/tutorials/feature-matrix.html | Sets expectations: e.g. multiple video tracks + audio + gaps + nesting in OTIO; adapter gaps for transitions/FCP. |
| **Writing an adapter** | https://opentimelineio.readthedocs.io/en/stable/tutorials/write-an-adapter.html | Construct/traverse timelines; multitrack vs single-track export patterns. |
| **Media linker** | https://opentimelineio.readthedocs.io/en/stable/tutorials/write-a-media-linker.html | Relink `MissingReference` → `ExternalReference` after EDL/AAF read. |
| **File bundles** (`.otioz` / `.otiod`) | https://opentimelineio.readthedocs.io/en/stable/tutorials/otio-filebundles.html | Ship cut + media together; flat `media/` basename rules. |
| **Environment variables** | https://opentimelineio.readthedocs.io/en/stable/tutorials/otio-env-variables.html | `OTIO_PLUGIN_MANIFEST_PATH`, default media linker, schema downgrade defaults. |

---

## 4. Tools & manipulation (reference behavior)

| Topic | URL | Why it matters for v1d.mt |
|--------|-----|---------------------------|
| **otiotool tutorial** | https://opentimelineio.readthedocs.io/en/stable/tutorials/otiotool.html | `--list-tracks`, `--video-only` / `--audio-only`, `--flatten`, `--stack`, `--concat`, `--trim`, `--remove-transitions` — documents expected multitrack operations. |
| **Quickstart** (install, Raven viewer, dev build) | https://opentimelineio.readthedocs.io/en/stable/tutorials/quickstart.html | `pip install opentimelineio`, timeline viewers for validating OTIO files during development. |

Console utilities (see Python module index): `otioconvert`, `otiocat`, `otiostat` — https://opentimelineio.readthedocs.io/en/stable/py-modindex.html

---

## 5. Python API modules (editing & algorithms)

Index: https://opentimelineio.readthedocs.io/en/stable/py-modindex.html

| Module | Doc path (stable) | Relevance |
|--------|-------------------|-----------|
| `opentimelineio.schema` | Under **Serialized schema** + py-modindex | `Timeline`, `Track`, `Stack`, `Clip`, `Gap`, `Transition`, references, markers. |
| `opentimelineio.opentime` | Serialized schema | `RationalTime`, `TimeRange`, `TimeTransform` — frame/rate math. |
| `opentimelineio.core` | Serialized schema | `Composition`, `Composable`, `enabled`, mutable sequence API on tracks/stacks. |
| `opentimelineio.adapters` | Architecture + write-an-adapter | `read_from_file` / `write_to_file`. |
| `opentimelineio.algorithms` | Source: [algorithms/](https://github.com/AcademySoftwareFoundation/OpenTimelineIO/tree/main/src/py-opentimelineio/opentimelineio/algorithms) | `stack_algo`, `track_algo`, `timeline_algo`, `filter` — flattening/filtering tracks (used by `otiotool --flatten`). |
| `opentimelineio.media_linker` | write-a-media-linker | Post-read relinking. |
| `opentimelineio.versioning` | versioning-schemas | Downgrade manifests. |

Python package overview: https://opentimelineio.readthedocs.io/en/stable/python_reference.html

---

## 6. Use cases (multitrack / conform workflows)

| Topic | URL |
|--------|-----|
| Conform new renders into the cut | https://opentimelineio.readthedocs.io/en/stable/use-cases/conform-new-renders-into-cut.html |
| Animation shot frame ranges changed | https://opentimelineio.readthedocs.io/en/stable/use-cases/animation-shot-frame-ranges.html |
| Shots added or removed from the cut | https://opentimelineio.readthedocs.io/en/stable/use-cases/shots-added-removed-from-cut.html |

These describe **visible frame range**, relinking, and cross-department timeline diff — typical goals once v1d.mt holds a real `Timeline`.

---

## 7. C++ / bindings (if v1d.mt links native OTIO)

| Topic | URL |
|--------|-----|
| C++ implementation | https://opentimelineio.readthedocs.io/en/stable/cxx/cxx.html |
| Language bridges | https://opentimelineio.readthedocs.io/en/stable/cxx/bridges.html |

---

## 8. Plugins reference (adapters shipped with OTIO)

| Topic | URL |
|--------|-----|
| Plugin documentation | https://opentimelineio.readthedocs.io/en/stable/tutorials/otio-plugins.html |

---

## 9. Implementation notes for v1d.mt (from docs, not OTIO code)

1. **Separation of concerns**: OTIO stores **edit decisions** and **composition rules**; media is **external** (`ExternalReference.target_url`). v1d `Engine` / NVDEC path stays per-clip; mt layer maps timeline time → active clip(s) + trim + track mix policy.
2. **Video mix**: Follow [Rendering](https://opentimelineio.readthedocs.io/en/stable/tutorials/otio-timeline-structure.html#rendering) — stack order, alpha composite; transitions = linear blend on one track.
3. **Audio mix**: Additive sum; doc recommends float sum + compression (v1d has no audio in PLAN_01 — explicit gap if mt adds audio).
4. **Gaps**: Transparent on multitrack stacks (lower tracks show through); solid black may need `GeneratorReference`, not a bare `Gap`.
5. **Effects**: `Effect` / `LinearTimeWarp` on clips — OTIO carries them; **playback interpretation is app-specific** except documented time-warp semantics.
6. **Editing UX**: OTIO does not specify UI; use time-range APIs for razor, slip, and playhead. `Track.kind` distinguishes video vs audio tracks.
7. **Interchange**: Prefer `.otio` for round-trip; use feature matrix before promising FCP/AAF transition fidelity.

---

## 10. External links (from OTIO docs home)

| Resource | URL |
|----------|-----|
| OpenTimelineIO home | https://opentimelineio.readthedocs.io/ |
| GitHub repository | https://github.com/AcademySoftwareFoundation/OpenTimelineIO |
| Discussion group | https://groups.google.com/g/opentimelineio |

---

## Read order (suggested)

1. Timeline structure → Time ranges → Architecture  
2. Serialized schema (`Track`, `Clip`, `Transition`) + File format specification  
3. Feature matrix + Adapters (+ write-an-adapter if importing EDL/AAF)  
4. otiotool tutorial (operational sanity checks)  
5. Use cases + versioning when persisting or exchanging timelines
