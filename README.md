# udemy-dl

fast, byte-sized CLI tool for locally backing up your udemy courses

> for personal backup only. Downloading courses may violate Udemy's ToS. Only download courses you own.

>**this project is provided as-is. It works, but it is not actively maintained and is far from perfect.
issues and pull requests are very welcome, though responses may be slow.**

---

## features

- fast curses TUI
- batch download
- resume interrupted downloads (state persisted to disk)
- quality selection (2160p → 360p)
- subtitle download (WebVTT → SRT conversion)
- supplementary materials download
- video integrity validation via `ffprobe`
- cross-platform: Linux, macOS, Windows, etc.

---

## requirements

- python 3.9+
- [`ffmpeg`](https://ffmpeg.org/download.html) in your `PATH` (required)
- `ffprobe` in your `PATH` (optional, enables video validation)

---

## installation

```bash
git clone https://github.com/alperien/udemy-dl.git
cd udemy-dl
pip install -e .
```

---

## getting your credentials

you need two values from your browser cookies after logging in to udemy:

1. open [udemy.com](https://www.udemy.com) and log in.
2. open **developer tools** (`F12`) → **application** tab → **cookies** → `https://www.udemy.com`.
3. copy:
   - `access_token` → this is your **token**
   - `client_id` → this is your **client_id**

---

## usage

```bash
udemy-dl
```

### headless mode

run without the interactive TUI:

```bash
# download all owned courses
UDEMY_TOKEN="..." UDEMY_CLIENT_ID="..." udemy-dl --headless

# download a specific course
udemy-dl --headless --course-id 12345

# override quality and skip extras
udemy-dl --headless --quality 720 --no-subtitles --no-materials
```

### shortcuts

| Key | Action |
|-----|--------|
| `j` / `↓` | Move down |
| `k` / `↑` | Move up |
| `Space` | Toggle course selection |
| `Enter` | Confirm / select |
| `q` / `Esc` | Back / quit |
| `Ctrl+C` | Abort download (progress saved) |

---

## configuration

config is in `~/.config/udemy-dl/config.json` (permissions: `600`).

## logs

logs are in `~/.config/udemy-dl/downloader.log`.

---

## development

```bash
git clone https://github.com/alperien/udemy-dl.git
cd udemy-dl
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

### tests

```bash
pytest
```

### linting

```bash
ruff check src/
black --check src/
mypy src/
```

---

## license

[MIT](LICENSE)
