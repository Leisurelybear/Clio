# Iteration Wave 2 — 2026-07-16 (Directions A → B → C)

TDD, multi-commit, docs updated. GPS/GPMF treated as **optional**.

## Verification

| Check | Result |
| --- | --- |
| pytest `clio/tests/test_gpmf.py` | 12 passed |
| vitest session/empty/toast/offline | green in session |
| Full suite | run at end of wave |

## Direction A — Editor workflow UX

| Commit | Summary |
| --- | --- |
| `e2df4af` | `resolveSessionRestore` + open lastEntity/lastVideo |
| `fd50744` | texts/voiceover empty states with Run / Rerun CTAs |
| `8a31153` | toast `aria-live` + 8s error default; status bar matches |

## Direction B — Media robustness

| Commit | Summary |
| --- | --- |
| `353cc8b` | pure `summarizeOfflineVideos` / `matchBatchRelink` |
| `9ee76b0` | offline summary bar + batch relink modal (filename match) |

## Direction C — GPMF (R-024 MVP)

| Commit | Summary |
| --- | --- |
| `6a5d473` | design doc + `clio/gpmf.py` (sidecar / marker probe / prompt format) |

### Optional GPS (user constraint)

- No GPS / no GPMF → `has_gpmf=False`, `format_telemetry_for_prompt` returns `""`, pipeline never blocked.
- Phone clips and missing paths covered by tests.
- Full binary GPMF parse and analyze-prompt wiring deferred to **R-024b**.

## How to use batch relink

1. Switch to **原视频**.
2. Offline bar shows count → **批量关联**.
3. Browse to folder with renamed/moved files → **扫描此目录并匹配** → **应用匹配**.

## How to experiment with GPMF (manual)

Place `CLIP.gpmf.json` next to `CLIP.MP4`:

```json
{
  "duration_sec": 120,
  "speed": [{"t_sec": 12.5, "value": 48, "unit": "km/h"}],
  "elevation_m": [100, 220]
}
```

Then in Python:

```python
from pathlib import Path
from clio.gpmf import load_telemetry_summary, format_telemetry_for_prompt
s = load_telemetry_summary(Path("CLIP.MP4"))
print(format_telemetry_for_prompt(s))
```

## Still open

| ID | Item |
| --- | --- |
| R-024b | Opt-in inject GPMF block into analyze context |
| A-006 | Static editor↔editor-config cycle |
