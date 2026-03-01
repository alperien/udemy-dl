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
- pipx for building

### windows

on Windows you also need:

- **`windows-curses`** – installed automatically by `pip install -e .` (declared in `pyproject.toml`). if you install dependencies manually, run:
  ```powershell
  pip install windows-curses
  ```
- **ffmpeg in your `PATH`** – the easiest ways to get it:
  ```powershell
  # winget (Windows 10 1709+)
  winget install --id Gyan.FFmpeg

  # or chocolatey
  choco install ffmpeg

  # or scoop
  scoop install ffmpeg
  ```
  alternatively, download a static build from [ffmpeg.org](https://ffmpeg.org/download.html#build-windows), extract it, and add the `bin` folder to your system `PATH`.
  verify installation with:
  ```powershell
  ffmpeg -version
  ffprobe -version
  ```
- **terminal** – use **Windows Terminal**, **PowerShell**, or **cmd.exe**. the curses-based TUI requires a terminal that supports standard escape sequences. **Git Bash / MSYS2 may not work correctly** with the interactive TUI; use `--headless` mode as a workaround.

---

## installation

```bash
git clone https://github.com/alperien/udemy-dl.git
cd udemy-dl
pipx install -e .
```

on Windows (PowerShell):

```powershell
git clone https://github.com/alperien/udemy-dl.git
cd udemy-dl
pip install -e .
```

> `windows-curses` is pulled in automatically on Windows via the platform marker in [`pyproject.toml`](pyproject.toml:13).

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

on Windows the default path is `C:\Users\<you>\.config\udemy-dl\config.json`.

## logs

logs are in `~/.config/udemy-dl/downloader.log`.

on Windows: `C:\Users\<you>\.config\udemy-dl\downloader.log`.

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
