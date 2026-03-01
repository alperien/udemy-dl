# udemy-dl

A lightweight terminal UI tool for locally backing up your owned Udemy courses.

> **For personal backup only.** Downloading courses may violate Udemy's Terms of Service. Only download courses you own and do not distribute downloaded content.

---

## Features

- Interactive curses TUI — no GUI required
- Multi-course selection and batch download
- Resume interrupted downloads (state persisted to disk)
- Quality selection (2160p → 360p with automatic fallback)
- Subtitle download (WebVTT → SRT conversion)
- Supplementary materials download
- Video integrity validation via `ffprobe`
- Retry logic with exponential backoff on network errors
- Cross-platform: Linux, macOS, Windows

---

## Requirements

- Python 3.9+
- [`ffmpeg`](https://ffmpeg.org/download.html) in your `PATH` (required)
- `ffprobe` in your `PATH` (optional — enables video validation)

---

## Installation

```bash
pip install udemy-dl
```

Or from source:

```bash
git clone https://github.com/yourname/udemy-dl.git
cd udemy-dl
pip install -e .
```

---

## Getting Your Credentials

You need two values from your browser cookies after logging in to Udemy:

1. Open [udemy.com](https://www.udemy.com) and log in.11
2. Open **Developer Tools** (`F12`) → **Application** tab → **Cookies** → `https://www.udemy.com`.
3. Copy the values of:
   - `access_token` → this is your **token**
   - `client_id` → this is your **client_id**

---

## Usage

```bash
udemy-dl
```

On first run (or if no config is found), you will be prompted to enter your credentials via the Settings screen.

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `j` / `↓` | Move down |
| `k` / `↑` | Move up |
| `Space` | Toggle course selection |
| `Enter` | Confirm / select |
| `q` / `Esc` | Back / quit |
| `Ctrl+C` | Abort download (progress saved) |

---

## Configuration

Configuration is stored in `~/.config/udemy-dl/config.json` (permissions: `600`).

You can also configure via environment variables (takes precedence over the config file):

| Variable | Default | Description |
|----------|---------|-------------|
| `UDEMY_TOKEN` | *(required)* | Your `access_token` cookie value |
| `UDEMY_CLIENT_ID` | *(required)* | Your `client_id` cookie value |
| `UDEMY_DOMAIN` | `https://www.udemy.com` | Udemy base URL |
| `UDEMY_DL_PATH` | `~/Downloads/udemy-dl` | Download destination directory |
| `UDEMY_QUALITY` | `1080` | Preferred video quality (`2160`, `1440`, `1080`, `720`, `480`, `360`) |
| `UDEMY_DOWNLOAD_SUBTITLES` | `true` | Download subtitle files |
| `UDEMY_DOWNLOAD_MATERIALS` | `true` | Download supplementary materials |
| `UDEMY_DL_CONFIG_DIR` | `~/.config/udemy-dl` | Override config/log directory |

---

## Output Structure

```
~/Downloads/udemy-dl/
└── Course Title/
    ├── 01 - Chapter Name/
    │   ├── 001 - Lecture Title.mp4
    │   ├── 001 - Lecture Title.en.srt
    │   └── 00-materials/
    │       └── slides.pdf
    └── 02 - Another Chapter/
        └── ...
```

---

## Logs

Logs are written to `~/.config/udemy-dl/downloader.log`.

---

## Development

```bash
git clone https://github.com/yourname/udemy-dl.git
cd udemy-dl
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

### Running tests

```bash
pytest
```

### Linting

```bash
ruff check src/
black --check src/
mypy src/
```

---

## License

[MIT](LICENSE)
