# Codebase Review: udemy-dl

**Rating: 7 / 10**

---

## Summary

`udemy-dl` is a compact CLI tool (~2,000 lines of application code, ~900 lines of tests) for backing up Udemy courses locally. It ships with both an interactive curses-based TUI and a headless mode, handles video downloads via ffmpeg, and supports subtitles plus supplementary materials. The project is well-structured for its scope, with clean separation of concerns, solid test coverage, and thoughtful touches like resume support and cross-platform compatibility. It loses points mainly on formatting/linting hygiene, a few architectural rough edges, and some gaps in error handling and documentation.

---

## Scoring Breakdown

| Category                        | Score | Weight | Notes |
|---------------------------------|-------|--------|-------|
| Project structure & organization| 8/10  | 15%    | Clean module split, good `src/` layout |
| Code quality & readability      | 6/10  | 20%    | Good logic, but pervasive formatting issues |
| Testing                         | 8/10  | 15%    | 104/105 passing, covers key paths |
| Error handling & resilience     | 7/10  | 15%    | Retry logic, graceful interrupts; some gaps |
| Architecture & design patterns  | 8/10  | 15%    | Protocol-based reporter, clean pipeline |
| Documentation                   | 6/10  | 10%    | Good README; sparse inline docs in places |
| Tooling & CI readiness          | 6/10  | 10%    | Tools configured but not enforced; lint fails |

**Weighted total: 6.95 -- rounded to 7/10**

---

## Strengths

### 1. Clean module separation

The codebase is split into well-scoped modules with clear single responsibilities:

- [`api.py`](src/udemy_dl/api.py) -- API client with retry logic
- [`dl.py`](src/udemy_dl/dl.py) -- download operations (ffmpeg, subtitles, materials)
- [`pipeline.py`](src/udemy_dl/pipeline.py) -- orchestration layer
- [`models.py`](src/udemy_dl/models.py) -- frozen dataclasses for domain objects
- [`state.py`](src/udemy_dl/state.py) -- atomic save/load of download progress
- [`tui.py`](src/udemy_dl/tui.py) -- all curses rendering in one place
- [`config.py`](src/udemy_dl/config.py) -- env var + file-based configuration
- [`exceptions.py`](src/udemy_dl/exceptions.py) -- clean exception hierarchy

This is a textbook layout for a project of this size.

### 2. Protocol-based progress reporting

The [`ProgressReporter`](src/udemy_dl/pipeline.py:31) protocol in `pipeline.py` decouples the download engine from both the TUI and headless reporters. This is a clean use of structural subtyping that makes testing straightforward (the test suite uses a simple `MockReporter`).

### 3. Robust download pipeline

The pipeline handles:

- **Resume support** via persisted `DownloadState` with atomic file writes (write-to-temp then `os.replace`)
- **Video validation** using ffprobe when available, graceful fallback when not
- **Quality fallback** -- tries preferred quality, falls back to lower, then HLS
- **Interrupt handling** -- SIGINT/SIGTERM caught, progress saved, partial files cleaned up
- **Cross-platform ffmpeg output reading** -- `select`-based on POSIX, threaded reader on Windows

### 4. Solid test suite

105 tests covering models, config, API, pipeline, state, TUI, utils, and CLI argument parsing. 104 pass. Tests use appropriate mocking and `tmp_path` fixtures. The test-to-code ratio (~0.45) is healthy for a project of this nature.

### 5. Good use of dataclasses

`Course` is frozen (immutable), `DownloadProgress` uses computed properties (`overall_percent`, `video_percent`), and `DownloadState` has clean serialization via `to_dict`/`from_dict`. The models are minimal and focused.

### 6. Security-conscious config handling

Config files are written with `0o600` permissions. Tokens are masked in the TUI settings view. The README explains exactly which cookies are needed without over-collecting credentials.

---

## Issues Found

### Critical

None.

### High Priority

#### H1. Pervasive formatting violations (647 ruff errors)

Every file has trailing whitespace on nearly every line, unsorted imports, and deprecated `typing` imports (`Dict`, `List`, `Tuple`, `Set` instead of builtins). The pre-commit config includes ruff and black, but they have clearly never been run against the current code. This means the pre-commit hooks are effectively decorative.

**Breakdown of 647 errors:**
- ~500 trailing whitespace (`W291`)
- ~15 unsorted import blocks (`I001`)
- ~10 deprecated typing imports (`UP035`)
- 2 unused imports (`F401`)
- 2 `os.*` calls that should use `Path.*` (`PTH105`, `PTH108`, `PTH123`)
- 2 suppressible try/except/pass blocks (`SIM105`)
- 1 unnecessary else-after-return (`RET505`)
- 1 collapsible nested if (`SIM102`)

All 575 of the auto-fixable errors could be resolved with `ruff check --fix` and `black .`.

#### H2. One failing test

[`test_skips_no_video_lecture`](tests/test_pipeline.py:111) fails because the test uses a `MagicMock` for `current_course_state` but `save_state()` tries to JSON-serialize it. The mock needs either a proper `DownloadState` instance or the `save_state` call needs to be patched.

#### H3. Unused import in `models.py`

[`field`](src/udemy_dl/models.py:2) is imported from `dataclasses` but only used in [`state.py`](src/udemy_dl/state.py). In `models.py` it is dead code flagged by ruff as `F401`.

### Medium Priority

#### M1. No CI pipeline

There is a `.github/` directory but no workflow files were found. The project has pytest, ruff, black, and mypy configured but nothing runs them automatically on push/PR. This explains how the formatting issues accumulated.

#### M2. Atomic writes use `os.replace` / `os.unlink` instead of `Path` equivalents

Both [`config.py`](src/udemy_dl/config.py:121) and [`state.py`](src/udemy_dl/state.py:77) use `os.replace()` and `os.unlink()` when the rest of the codebase consistently uses `pathlib.Path`. This is flagged by ruff's `PTH` rules and breaks consistency.

#### M3. Token visible in process list

The ffmpeg command in [`download_video()`](src/udemy_dl/dl.py:236) passes the bearer token via `-headers`, which means it is visible in `ps` output. The docstring acknowledges this, but a headers file (even a temporary one with `0o600` permissions) would be more secure. ffmpeg does not natively support this, but a named pipe or temp file approach would mitigate the risk.

#### M4. `_webvtt_to_srt` is complex and could use more edge-case tests

The function at [`dl.py:31`](src/udemy_dl/dl.py:31) handles timestamp normalization, HTML stripping, and format conversion in ~55 lines. While tested, the tests do not cover multi-line cues, overlapping timestamps, or malformed WebVTT (e.g., missing blank lines between cues).

#### M5. `download_materials` has deep nesting

The [`download_materials()`](src/udemy_dl/dl.py:325) method has 5+ levels of indentation with interleaved interrupt checks, retry logic, and file cleanup. Extracting the per-asset download into a helper method would improve readability.

### Low Priority

#### L1. No type: ignore or mypy strictness

mypy is listed as a dev dependency and in pre-commit, but there is no `mypy.ini` or `[tool.mypy]` section in `pyproject.toml`. Running mypy in strict mode would likely surface issues with the `Dict`, `Any`, and `Optional` usage patterns.

#### L2. Module docstrings are inconsistent

[`dl.py`](src/udemy_dl/dl.py:1) and [`main.py`](src/udemy_dl/main.py:1) have good module-level docstrings. [`api.py`](src/udemy_dl/api.py), [`app.py`](src/udemy_dl/app.py), [`config.py`](src/udemy_dl/config.py), [`pipeline.py`](src/udemy_dl/pipeline.py), and [`tui.py`](src/udemy_dl/tui.py) have none.

#### L3. Magic numbers

- `FFMPEG_TIMEOUT = 600` in [`dl.py`](src/udemy_dl/dl.py:24) -- good, named constant
- `maxlen=100` for the log buffer in [`app.py`](src/udemy_dl/app.py:56) -- undocumented
- `1024` byte threshold for "partial file" detection in [`pipeline.py`](src/udemy_dl/pipeline.py:209) -- should be a named constant

#### L4. `_HeadlessReporter.on_progress` is a no-op

[`_HeadlessReporter.on_progress()`](src/udemy_dl/main.py:38) does nothing. For headless mode, even a simple percentage line to stdout would improve the user experience for long-running batch downloads.

#### L5. `__init__.py` has formatting inconsistency

[`__init__.py`](src/udemy_dl/__init__.py:1) has `__version__ ="2.1.0"` with a missing space before `=`.

---

## Recommendations (prioritized)

1. **Run `ruff check --fix . && black .`** to clear the 575 auto-fixable errors, then manually fix the remaining ~70. This is a 5-minute task that eliminates the majority of issues.

2. **Add a GitHub Actions CI workflow** with at minimum: `ruff check`, `black --check`, `pytest`, and optionally `mypy`. This prevents regressions.

3. **Fix the failing test** in `test_pipeline.py` by using a real `DownloadState` instead of `MagicMock` for `current_course_state`.

4. **Remove unused imports** (`field` in `models.py`, `set_secure_permissions` in the flagged location).

5. **Add `[tool.mypy]` config** to `pyproject.toml` and run mypy to catch type issues early.

6. **Refactor `download_materials()`** to extract per-asset download logic into a smaller helper.

7. **Add headless progress output** so batch users get feedback during long downloads.

---

## Conclusion

This is a well-designed small project with good architectural instincts -- the module boundaries are clean, the protocol pattern is well-applied, and the download pipeline is resilient. The main drag on the score is the formatting state: every file is covered in trailing whitespace and unsorted imports, which suggests the tooling was configured but never integrated into the workflow. Fixing the lint issues and adding CI would easily push this to an 8/10. The core logic is solid and the test coverage is above average for a personal project.
