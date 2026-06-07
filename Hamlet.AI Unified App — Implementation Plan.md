# Hamlet.AI Unified App — Implementation Plan (Revised)

## Context

The repo today has two single-file CLI tools that share an ElevenLabs account but are otherwise independent:

- **`voiceclone2.py` (264 lines)** — voice-clone pipeline for the ghost-cue show. Operator drops volunteer audio into `~/Desktop/VOICE-CLONE/SAMPLE/`, the script clones via ElevenLabs IVC, polls for ready, parses `clone.txt`, synthesizes pre-scripted lines to `LINES/` for QLab. Has a **race condition** today: `clone_voice`, `cleanup`, and `parse_script` run concurrently, and `cleanup()` can move files out of `SAMPLE/` while `clone_voice()` is still reading from it.
- **`Hamlet-gen5.py` (363 lines, canonical filename — was `Hamletgen5.py` in earlier scaffolding)** — Shakespeare-scene generator for the LLM-H production. Takes six `input()` prompts, calls Anthropic/OpenAI/Ollama, translates to German via Ollama, splits into per-character per-line files, runs ElevenLabs TTS with hardcoded character→voice_id mapping (HAMLET/GERTRUDE/POLONIUS), and **moves** everything to `~/Desktop/LLM-H/` (destructive, blocks re-runs). Ships with a **hardcoded ElevenLabs API key** on line 204.

Goal: collapse both into a single PySide6 application backed by a shared `hamlet_ai` core module, with show-night safety as the top priority. The GUI gives the operator clear progress bars, edit checkpoints at every stage, in-app playback, a persistent voice library with consent metadata, a Show Mode that locks risky controls, and explicit fallback options when something goes wrong. A single `hamlet-ai` CLI with subcommands (`gui`, `script-gen`, `voice-clone`, `doctor`) preserves headless usage. Full pytest pyramid (unit + integration + GUI) runs headless on Linux.

## Confirmed Design Decisions (carried + revised)

- **App shape**: two independent tools in one app shell, no data handoff.
- **PySide6** GUI framework; `pytest-qt` for GUI tests.
- **Storage**: keep `~/Desktop/VOICE-CLONE/` and `~/Desktop/LLM-H/` paths; **add per-run subfolders** under `VOICE-CLONE/RUNS/{timestamp}/` to fix the cleanup race.
- **LLM providers**: Anthropic + OpenAI + Ollama. Updated default model IDs, editable in Settings, **with per-provider Test Connection buttons** and last-tested timestamps.
- **Translation**: **split first, then translate per dialogue line**, preserving character labels and line IDs. Operator-pinnable per-tool LLM.
- **CLI**: `hamlet-ai {gui,script-gen,voice-clone,doctor}`. Old `voiceclone2.py` and `Hamlet-gen5.py` become thin shims.
- **Character→voice map**: persistent JSON, GUI-editable; per-line override (ephemeral).
- **Edit checkpoints in Script Gen**: after generation, after translation, after line splitting, before TTS.
- **Voice Library carry-overs**: recent clones list, inline clone.txt editor, in-GUI playback + archive browser — **now extended with consent + retention metadata** (see new schema).
- **Recording UX**: target 90s (configurable), 3-2-1 prep countdown, count-down to 0 with level meter, auto-stop at 0, manual Stop, retry/discard.
- **Workspace re-runs**: Script Gen copies (not moves) to Desktop and keeps timestamped workspace artifacts; "Reset workspace" is explicit and confirmed.
- **Test mocking**: hand-written SDK stubs for unit tests; recorded JSON fixtures for integration tests.

## Five high-risk areas this revision addresses

1. **Secrets**: hardcoded ElevenLabs key in git history (Hamlet-gen5.py:204).
2. **Cleanup/clone race condition** in voiceclone2.py.
3. **Consent + retention** of cloned voice data.
4. **Dry-run correctness** (text-with-.mp3-extension is not playable; current voiceclone2 also raises at import without API key even in DRY_RUN).
5. **Model/provider fragility** (default model IDs change; Ollama daemon may be down; current SDK shapes drift).

## Architecture

```
/home/user/repo/
├── pyproject.toml                          # extras: [core] [gui] [audio] [providers] [dev]
├── README.md                               # operator-facing GUI walkthrough + show-night checklist
├── voiceclone2.py                          # SHIM → hamlet_ai.cli.main(["voice-clone"])
├── Hamlet-gen5.py                          # SHIM → hamlet_ai.cli.main(["script-gen", "--interactive"])
├── src/hamlet_ai/
│   ├── __init__.py / __main__.py
│   ├── cli.py                              # gui | script-gen | voice-clone | doctor
│   ├── config.py                           # AppConfig + show_mode + retention + show_profile
│   ├── consent.py                          # ConsentRecord, gating helpers
│   ├── migration.py                        # first-run inventory + backup of existing dirs
│   ├── core/
│   │   ├── elevenlabs.py                   # ElevenLabsClient (timeouts, retries, redacted logs, delete_voice, list_voices, schema validation)
│   │   ├── audio/
│   │   │   ├── recorder.py                 # AudioRecorder(QObject)
│   │   │   ├── playback.py                 # AudioPlayer(QObject)
│   │   │   └── silent_audio.py             # write a real, short, silent mp3/wav for DRY_RUN
│   │   ├── voice_clone/
│   │   │   ├── pipeline.py                 # run_show() — NO cleanup-during-clone race
│   │   │   ├── runs.py                     # RunFolder (creates RUNS/{timestamp}/, atomic ops)
│   │   │   ├── voice_library.py            # extended VoiceEntry schema
│   │   │   └── script_model.py             # editable clone.txt
│   │   └── script_gen/
│   │       ├── prompt.py                   # ScriptGenParams + construct_prompt
│   │       ├── llm.py                      # LLMProvider + generate + test_connection
│   │       ├── translation.py              # per-line translation, label-preserving
│   │       ├── line_splitter.py            # tolerant splitter (apostrophes, hyphens, accents, colons in dialogue)
│   │       ├── character_voices.py         # persistent character→voice_id map
│   │       ├── tts.py                      # synthesize_line()
│   │       └── export.py                   # copy_to_desktop() with overwrite confirmation
│   └── gui/
│       ├── app.py / main_window.py         # toolbar + LogPane dock + tab switcher + Show Mode
│       ├── workers.py
│       ├── settings_dialog.py
│       ├── show_mode.py                    # Show Mode bar + lock/unlock logic
│       ├── status_bar.py                   # Big status indicators
│       ├── consent_dialog.py               # operator-facing consent confirmation
│       ├── widgets/                        # level_meter, countdown_timer, log_pane, play_button, script_editor, status_pill
│       ├── voice_clone/                    # tab + record / library / scripted_lines / adhoc_tts / archive sub-tabs
│       └── script_gen/                     # stepper + input/generate/translation/splitter/voices/tts/export stages
└── tests/
    ├── conftest.py / fixtures/             # recorded LLM + ElevenLabs JSON
    ├── unit/                               # one file per core module + consent + migration + runs
    ├── integration/                        # voice clone, script gen, record→clone→synth, CLI doctor
    └── gui/                                # one file per tab/stage + workers + show_mode + consent_dialog
```

**Top window**: `QMainWindow` with **persistent status bar** (Ready / Recording / Cloning / Generating / QLab files ready / Failed / DRY_RUN ON / No API key) + toolbar (Show Mode toggle, DRY_RUN toggle, API-key indicator with green/yellow/red, Settings, Doctor) + central `QTabWidget` (Script Generation = stepper, Voice Clone = sub-tabs) + bottom `LogPane` (with redaction).

**Pipeline change — no more concurrent cleanup**: every voice-clone session creates `VOICE-CLONE/RUNS/{ts}/` and writes its sample, metadata, and generated lines there. `cleanup` only archives the **previous** run after the new run succeeds (or operator triggers it). The race condition disappears because the active sample is never moved out from under `clone_voice()`.

**Atomic writes**: every persistent write (`synthesize`, `ScriptDocument.save`, `VoiceLibrary.save`, `CharacterVoiceMap.save`, `settings.json`, run metadata) uses `.tmp` + `os.replace`. Bonus: `clone_metadata.json` per run records voice_id, consent record, target seconds, API model, and retention policy.

## Milestones

### Milestone 1 — Safe core refactor, no GUI yet

Goal: rip the dangerous parts out of the legacy scripts, restructure the package, and put a tested core in place. The legacy CLIs keep working as shims.

**Step 0 — Security, cleanup, and inventory** *(NEW)*
- Operator rotates the exposed ElevenLabs key at the ElevenLabs dashboard (out-of-band; flagged in PR).
- Scrub the hardcoded key from `Hamlet-gen5.py:204`; route both tools through `ELEVENLABS_API_KEY` in `.env`.
- Standardize the canonical legacy filename as **`Hamlet-gen5.py`** (rename the scaffolded `Hamletgen5.py` shim to match).
- Add `tests/unit/test_no_hardcoded_secrets.py` that greps the tracked source tree for `sk_…`, `sk-ant-…`, `sk-…` patterns and fails on any hit.
- Add `src/hamlet_ai/migration.py` that on first run: (a) inventories `~/Desktop/VOICE-CLONE/` and `~/Desktop/LLM-H/` (counts files, finds `clone.txt`, finds archives, finds stale samples), (b) writes a timestamped backup copy to `~/Desktop/VOICE-CLONE.backup-{ts}/` and `~/Desktop/LLM-H.backup-{ts}/` before any write that could clobber existing artifacts, (c) records the inventory in `~/.config/hamlet-ai/first_run_inventory.json`.

**Step 1 — Project scaffold (extras-based)**
- `pyproject.toml` with package extras:
  - `[core]` = `requests`, `python-dotenv`
  - `[providers]` = `anthropic`, `openai`, `ollama`
  - `[audio]` = `sounddevice`, `numpy`, `soundfile`
  - `[gui]` = `PySide6`
  - `[dev]` = `pytest`, `pytest-qt`, `pytest-mock`, `responses`
- Default install (`pip install hamlet-ai`) pulls `[core]`; CI runs `pip install -e ".[core,providers,audio,gui,dev]"`.
- Shims for `voiceclone2.py` + `Hamlet-gen5.py` still importable.

**Step 2 — `AppConfig` + settings persistence + Show Mode + retention**
- `AppConfig` adds: `show_mode: bool`, `show_profile: str` (single profile in v1, multi-show-ready), `retention: RetentionSettings` (sample TTL, archive TTL, generated-files TTL, default ephemeral-show-mode flag), `provider_health: dict[str, ProviderHealth]` (last_tested, status), `recording_target_seconds`.
- `default_config()` reads `~/.config/hamlet-ai/settings.json`. Never persists API keys.
- Atomic save.

**Step 3 — `RunFolder` model + safe voice-clone pipeline**
- New `core/voice_clone/runs.py`: `RunFolder.create_for_now()` → `VOICE-CLONE/RUNS/{ts}/` with `sample/`, `generated_lines/`, `clone_metadata.json`, `run_log.txt`.
- `pipeline.run_show(cfg)` flow:
  1. Confirm consent (raises if not provided in the cfg/run context).
  2. Create new `RunFolder`.
  3. **Copy** the supplied sample into the run folder (don't move).
  4. **Sequentially** (not concurrently): `clone_voice` → `wait_for_voice` → write `clone_metadata.json` → `parse_script` → `generate_lines` into `RunFolder.generated_lines/`.
  5. **Then**, on success, archive previous `LINES/` content into `ARCHIVE/{prev_ts}/`, swap the run's generated_lines into `LINES/` atomically (one-by-one `os.replace`), and append the new entry to `VoiceLibrary` with `consent_confirmed=True, consent_timestamp=...`.
  6. On failure, leave `LINES/` untouched. Add a `restore_last_good(cfg)` helper that lists previous archives and restores any selected one.
- `cleanup()` is no longer racy because it never runs concurrently with clone.

**Step 4 — Voice library schema extension + ScriptDocument**
- `VoiceEntry` schema: `voice_id`, `label`, `created_at`, `sample_path`, `sample_filename`, `consent_confirmed`, `consent_timestamp`, `retention_policy` (`"keep"|"ephemeral"|"delete_after_show"`), `remote_deleted: bool`, `provider_metadata: dict` (model, settings, run_ts).
- `VoiceLibrary` adds: `delete_local(voice_id)`, `delete_remote(voice_id, client)`, `delete_both(voice_id, client)`, `sweep_expired(now)` (consults retention policy + TTL).
- `ScriptDocument` unchanged (editable clone.txt model).

**Step 5 — Hamlet-gen5 prompt + LLM dispatch + connectivity tests**
- `core/script_gen/prompt.py` and `core/script_gen/llm.py` as before, plus:
- `llm.test_connection(provider, cfg)` makes a tiny request (`messages.create` with 1 token / `chat.completions` with `messages=[{role:user,content:"ping"}]` / `ollama.list()`) and returns `(ok: bool, message: str)`. Records to `cfg.provider_health[provider].last_tested`.
- Ollama branch detects daemon-down (`ollama.ResponseError` / `ConnectionError`) and surfaces a specific error.

**Step 6 — Script Gen tolerant splitter + label-preserving translation + export**
- Splitter:
  - Allow names with apostrophes, hyphens, spaces, accented characters (`KING'S MESSENGER`, `JEAN-PAUL`, `ÉLODIE`).
  - Handle colons inside dialogue (`HAMLET: To eat: or not.`).
  - Preserve source line order and assign stable `line_id` (UUIDs or `line_number`-derived).
  - Distinguish `spoken: bool` from `text_only: bool` (for stage directions kept as comments).
  - Expose `rejected` lines with their reason code so the GUI can show them.
- Translation:
  - `translate_scene(parsed: ParsedScript, cfg, target_language) → ParsedScript` translates dialogue **line-by-line** with a system prompt instructing the LLM to preserve the `CHARACTER:` prefix verbatim.
  - Returns same line count and same `line_id`s. If counts diverge, raises `TranslationCountMismatch` so the GUI can show a validation warning.
- `tts.synthesize_line` uses real silent mp3 in DRY_RUN (see Step 7).
- `export.copy_to_desktop` copies, never moves. Adds: timestamped workspace artifacts, "Preview destination" output, "Overwrite confirm" callback hook for the GUI, explicit `reset_workspace(confirm=True)` only.

**Step 7 — Dry-run correctness + ElevenLabsClient hardening**
- `core/audio/silent_audio.py`: produce a real ~0.5s silent mp3 (or wav fallback) by writing a known-good MP3 frame to disk; used by both pipelines in DRY_RUN. Files are valid for QLab + QMediaPlayer + the in-app player.
- DRY_RUN: when `cfg.dry_run=True`, an absent `ELEVENLABS_API_KEY` is **not** an error. When `dry_run=False`, missing/invalid key blocks the run with a clear error.
- `ElevenLabsClient` updates:
  - Per-call timeout (default 30s, configurable via cfg).
  - Retry with exponential backoff (3 retries) for 429 + 5xx; no retry for 4xx (except 408).
  - Specific exception classes: `AuthError` (401), `BadAudioError` (422), `QuotaError` (402/403 "quota"), `RateLimitError` (429), `Timeout` (408/timeout).
  - Redacted logging: never log the key or the audio bytes; log status codes, voice_ids, timing.
  - `list_voices()`, `delete_voice(voice_id)`, response schema validation (`pydantic` or hand-rolled with explicit `KeyError` → `BadResponseError`).
  - Atomic audio write helper.

**Step 8 — Audio recorder + player core** *(unchanged from previous plan; QueuedConnection-safe signals)*

**Step 9 — QThread workers**
- Same set as before, plus a `DoctorWorker` for `hamlet-ai doctor` runs (used by both CLI and a future GUI doctor panel).

**Step 10 — `hamlet-ai doctor` + Show Mode infra** *(NEW CLI cmd)*
- `cli doctor` runs checks and prints a colored report:
  - ElevenLabs key set + `list_voices()` returns 200
  - Anthropic / OpenAI / Ollama `test_connection` results
  - macOS microphone permission (best-effort: try a 0.1s `sounddevice.InputStream` and report)
  - Write access to `VOICE-CLONE/RUNS/`, `VOICE-CLONE/LINES/`, `LLM-H/`
  - `clone.txt` exists + parses + lists ghost cue filenames
  - QLab-facing filenames present (`LINES/ghost_*.mp3`)
  - Stale samples sitting in legacy `SAMPLE/`
  - Voice library entries with `remote_deleted=False` and retention `"delete_after_show"` past TTL (warn)
  - DRY_RUN status
  - Available audio input devices
- Exit code: `0` = all green, `1` = warnings, `2` = errors.

### Milestone 2 — Voice Clone GUI, show-safe

**Step 11 — GUI shell + Settings dialog + Show Mode bar + Big status bar**
- Toolbar adds: Show Mode toggle, Doctor button.
- API-key indicator now traffic-light: **green** = tested OK (within last hour), **yellow** = present but untested or stale, **red** = missing / last-test failed.
- Status bar across bottom (above LogPane) with big-text status pills: Ready / Recording / Cloning / Generating / QLab Ready / Failed / DRY_RUN / No API Key.
- Show Mode lock rules:
  - Disables Settings, Reset Workspace, Delete Voice, Restore from Archive (without confirmation), Edit Character Voices.
  - Adds prominent fallback buttons: **Restore last good LINES/**, **Use stock Ghost voice** (a built-in voice_id), **Regenerate selected line**, **Open QLab folder** (Finder).

**Step 12 — Consent dialog + Record tab**
- `ConsentDialog`: blocking modal shown the first time Record is clicked per volunteer. Text: "This records the volunteer, uploads the sample to ElevenLabs, creates a voice clone, and generates lines in that voice. Tap Confirm only if the volunteer has consented to this." Records `ConsentRecord` into `RunFolder.clone_metadata.json`.
- Record tab unchanged structurally from earlier draft, BUT:
  - Recording target + 3-2-1 prep + count-down to 0 + auto-stop + manual Stop + Retry — all retained.
  - Adds: "Mic check" button that opens a 0.5s test stream and reports RMS; shows a clear dialog directing to System Settings if denied.
  - "Clone This Recording" calls into the new sequential pipeline (RunFolder) — the worker now reports retention choice (Keep / Ephemeral / Delete after show).

**Step 13 — Voice Library + Scripted Lines + Ad-hoc + Archive sub-tabs**
- Voice Library columns now show: Label, Voice ID, Created, Sample, Consent ✓, Retention, Remote ✗ (deleted flag).
- Buttons: Set Active, Play Sample, Rename, **Delete (local only)**, **Delete (local + ElevenLabs)** (calls `client.delete_voice`), Mark Ephemeral.
- Sweep button: "Delete expired clones now" runs `VoiceLibrary.sweep_expired(now)`.
- Scripted Lines unchanged structurally (editable clone.txt, per-row Play, generate selected/all).
- Ad-hoc tab unchanged (output to `ADHOC/`).
- Archive: list `ARCHIVE/{ts}/` desc, file table with per-row Play, **Restore last good LINES/** button (copies a selected archive subfolder into LINES/, atomic per file). This is the show-night rescue path.

### Milestone 3 — Script Gen GUI

**Step 14 — Stepper shell + Input + Generate stages**
- Stepper unchanged.
- Input stage validates ScriptGenParams; LLM picker shows traffic-light per provider with a "Test Connection" button.
- Generate stage shows constructed prompt readonly, Generate spawns `LLMGenerationWorker`, result editable, Regenerate/Save/Next.

**Step 15 — Splitter + Translation (per-line) + Voices + TTS + Export stages**
- Splitter stage: Run Splitter → table of `(line_id, character, dialogue, spoken?, status)`; rejected collapsible section with reason codes and "repair" affordance (move into Valid).
- Translation stage: per-line translation; if line count diverges from English, show a yellow warning bar with side-by-side diff before allowing Next.
- Voices stage: characters × picker (loaded from cached ElevenLabs `list_voices` with refresh button); per-line override column. Save Map persists.
- TTS stage: progress bar per line, per-row Play; in DRY_RUN writes silent mp3s; logs per-line elapsed and total time for the perf-budget acceptance criterion (Step 17).
- Export stage:
  - Preview tree of intended Desktop layout vs current Desktop contents.
  - "Confirm Overwrite" dialog when any existing file would be replaced.
  - Copy to Desktop button. Never moves. Workspace retained.
  - Reset Workspace button shows confirm dialog.

### Milestone 4 — Polish, packaging, CI, docs

**Step 16 — Performance budget + timed run logging**
- Worker-side timers record: record-stop → clone ready, clone ready → all lines generated, total.
- Voice Clone result panel shows actual vs target (default 2 minutes from README).
- If total exceeds target, surface fallback buttons (Use stock Ghost voice, Restore last good).
- Logged into `run_log.txt` inside the RunFolder.

**Step 17 — Integration tests + high-risk tests**
- New tests on top of the unit pyramid:
  - `test_pipeline_cleanup_does_not_move_current_sample` — assert sequential ordering.
  - `test_dry_run_works_without_api_key` — instantiate AppConfig with no key, DRY_RUN=True, full pipeline succeeds.
  - `test_dry_run_audio_is_playable` — feed the generated DRY_RUN mp3 into a stub QMediaPlayer and assert it reports a non-zero duration (or skip with reason if QMediaPlayer decoder isn't installed in CI; in that case assert file length > 0 and an MP3 magic-number check).
  - `test_atomic_writes_no_partial_file_visible` — patch `os.replace` to raise after the `.tmp` write; assert the destination is absent and the `.tmp` is cleaned.
  - `test_voice_library_remote_delete_called` — `delete_both` invokes `client.delete_voice`.
  - `test_consent_required_before_cloning` — without consent in cfg/run, `run_show` raises `ConsentNotProvided`.
  - `test_translation_preserves_speaker_labels` — translated `ParsedScript` has identical characters set and line_id list.
  - `test_splitter_handles_colons_in_dialogue` — `HAMLET: To eat: or not.` → character `HAMLET`, dialogue `To eat: or not.`.
  - `test_splitter_handles_accented_and_hyphenated_names` — `JEAN-PAUL`, `ÉLODIE`, `KING'S MESSENGER` all parse.
  - `test_qlab_filenames_remain_fixed` — after generate, `LINES/ghost_*.mp3` filenames match expected list verbatim.
  - `test_restore_last_good_lines_copies_archive_into_lines` — pick an archive, restore, verify LINES/.
  - `test_provider_test_connection_handles_failure_gracefully` — mock each SDK to raise, assert `test_connection` returns `(False, message)`.
  - `test_logs_redact_api_keys` — feed a fake log line containing `el-key-secret` through the redactor and assert it's masked.
- Existing pyramid stays.

**Step 18 — Packaging + launchers + README**
- `pip install hamlet-ai[gui,audio,providers,dev]` works.
- `hamlet-ai gui` and `hamlet-ai doctor` are documented as the supported entry points.
- Optional macOS `.command` shell launcher script (`scripts/hamlet-ai.command`) that activates the venv and runs `hamlet-ai gui`.
- Optional py2app `.app` recipe is documented but not built in CI (out of scope for v1).
- README sections: Install / First run + migration / GUI walkthrough (per tool) / Settings / Doctor / Show Mode / **Pre-show startup checklist** / Troubleshooting.

**Step 19 — CI**
- GitHub Actions: lint + `QT_QPA_PLATFORM=offscreen pytest tests/ -v` on Linux.
- macOS smoke job is documented but not automated (audio + TCC make it impractical on hosted runners).

## Consent and Retention

- **Consent record** (always required before any clone): `{volunteer_label, confirmed_at, confirmed_by_operator, retention_policy}`. Stored in the RunFolder's `clone_metadata.json` and on the VoiceEntry.
- **Retention policies**: `"keep"` (default), `"ephemeral"` (deleted at end of session: local sample + library entry + remote ElevenLabs voice), `"delete_after_show"` (sweep at next launch after a configurable TTL — default 24h).
- **GUI deletion controls**: Voice Library exposes Delete (local only) and Delete (local + ElevenLabs). The latter calls `client.delete_voice` and on success sets `remote_deleted=True`.
- **Ephemeral Show Mode**: a global toggle that sets every new clone's `retention_policy="ephemeral"`. On app shutdown (or explicit "End show"), all ephemeral clones are deleted both locally and via the ElevenLabs API.
- **Log redaction**: every log message that touches an API key, a personal voice label, or sample path goes through `redact()` before reaching the LogPane / `run_log.txt`. Keys are replaced by `<REDACTED>`; voice labels are replaced by `<volunteer>` when Show Mode is on.

## Test Plan (full pyramid)

**Unit** (`tests/unit/`): one file per core module — `test_config`, `test_pipeline`, `test_runs`, `test_voice_library`, `test_script_model`, `test_elevenlabs_client`, `test_prompt`, `test_llm`, `test_translation`, `test_line_splitter`, `test_character_voices`, `test_tts`, `test_export`, `test_recorder`, `test_playback`, `test_consent`, `test_migration`, `test_silent_audio`, `test_no_hardcoded_secrets`, `test_redaction`.

**Integration** (`tests/integration/`): `test_voice_clone_full_pipeline`, `test_script_gen_full_pipeline`, `test_record_to_clone_to_synth`, `test_cli_subcommands` (incl. `doctor`), plus the high-risk tests listed in Step 17.

**GUI** (`tests/gui/`): one file per tab/stage — `test_main_window`, `test_show_mode`, `test_consent_dialog`, `test_record_tab`, `test_voice_library_tab`, `test_scripted_lines_tab`, `test_adhoc_tts_tab`, `test_archive_tab`, `test_input_stage`, `test_generate_stage`, `test_translation_stage`, `test_splitter_stage`, `test_voices_stage`, `test_tts_stage`, `test_export_stage`, `test_workers`.

**Headless CI**: `QT_QPA_PLATFORM=offscreen pytest tests/ -v`.

## Verification

- **DRY_RUN on**: no API key required; the full pipeline runs end-to-end without hitting ElevenLabs.
- **Dry-run files are valid playable audio** (silent mp3/wav), confirmed by playback test.
- **Voice Clone full run completes under target time** (2 min default) OR the Voice Clone result panel surfaces fallback buttons.
- **Show Mode locks risky controls**: Settings disabled, Delete buttons require explicit confirm, Reset Workspace blocked.
- **`hamlet-ai doctor` passes before show**: all checks green or explicitly acknowledged warnings.
- **One real ElevenLabs round-trip is tested before rehearsal** (operator turns DRY_RUN off and runs a 5-second clone).
- **Legacy shims still work**: `python voiceclone2.py` and `python Hamlet-gen5.py` route through the new CLI.
- **No hardcoded secrets test** stays green on every PR.
- **Consent dialog appears before any clone** in a non-test environment.

## Status of work already done against the OLD plan

(So we know what to redo vs keep.)

- ✅ Steps 1–11 of the previous plan are implemented (~179 tests green) covering: pyproject, config, pipeline extraction, voice library, prompt + LLM dispatch, translation, line splitter, character voices, TTS, export, CLI subcommands, recorder, player, workers, MainWindow + Settings, Record tab.
- ⚠️ **Needs revisit under this revised plan**:
  - Filename `Hamletgen5.py` → rename to `Hamlet-gen5.py` (Step 0).
  - Pipeline still uses concurrent `ThreadPoolExecutor` for clone+cleanup+parse → replace with sequential RunFolder flow (Step 3).
  - DRY_RUN still writes text-with-.mp3 → switch to real silent mp3 (Step 7).
  - voiceclone2.py shim still reads `os.environ["ELEVENLABS_API_KEY"]` at import → make DRY_RUN-friendly (Step 7).
  - VoiceEntry schema lacks consent + retention fields → extend (Step 4).
  - ElevenLabsClient lacks timeouts, retries, redacted logs, `delete_voice`, schema validation → harden (Step 7).
  - Line splitter rejects apostrophes-in-names beyond `KING'S`; doesn't keep line_id; doesn't handle colons in dialogue → expand (Step 6).
  - Translation translates the whole scene at once; doesn't preserve labels → rewrite to per-line (Step 6).
  - No consent gating, no Show Mode, no Doctor, no migration, no silent_audio module → add (Steps 0, 10, 11, 12).
  - pyproject deps are one flat list → split into extras (Step 1 revision).

## Critical files

- `/home/user/repo/pyproject.toml` (extras)
- `/home/user/repo/src/hamlet_ai/config.py` (Show Mode + retention)
- `/home/user/repo/src/hamlet_ai/consent.py` (NEW)
- `/home/user/repo/src/hamlet_ai/migration.py` (NEW)
- `/home/user/repo/src/hamlet_ai/core/elevenlabs.py` (timeouts, retries, delete_voice, redaction)
- `/home/user/repo/src/hamlet_ai/core/audio/silent_audio.py` (NEW)
- `/home/user/repo/src/hamlet_ai/core/voice_clone/runs.py` (NEW — RunFolder)
- `/home/user/repo/src/hamlet_ai/core/voice_clone/pipeline.py` (sequential; uses RunFolder)
- `/home/user/repo/src/hamlet_ai/core/voice_clone/voice_library.py` (extended schema)
- `/home/user/repo/src/hamlet_ai/core/script_gen/line_splitter.py` (tolerant; stable line_id)
- `/home/user/repo/src/hamlet_ai/core/script_gen/translation.py` (per-line, label-preserving)
- `/home/user/repo/src/hamlet_ai/gui/main_window.py` (Show Mode, status bar)
- `/home/user/repo/src/hamlet_ai/gui/show_mode.py` (NEW)
- `/home/user/repo/src/hamlet_ai/gui/consent_dialog.py` (NEW)
- `/home/user/repo/src/hamlet_ai/gui/voice_clone/archive_tab.py` (Restore last good)
- `/home/user/repo/src/hamlet_ai/cli.py` (`doctor` subcommand)
- `/home/user/repo/voiceclone2.py` (shim, key scrubbed, DRY_RUN-friendly)
- `/home/user/repo/Hamlet-gen5.py` (canonical filename, shim, key scrubbed)