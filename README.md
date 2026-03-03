# udemy-dl

fast, byte-sized CLI tool for locally backing up your udemy courses


>*this project is provided as-is. It works, far from perfect tho. PRs and issues are welcome.*

---

## features

- fast curses TUI
- batch download
- resume interrupted downloads
- quality selection
- subtitle download
- supplementary materials download
- cross-platform: Linux, macOS, Windows, etc.

---

## requirements

- `python 3.9+`
- [`ffmpeg`](https://ffmpeg.org/download.html) in your `PATH` (required)
- `ffprobe` in your `PATH` (optional, enables video validation)
- `pipx` for global install (optional)

### windows

on windows you also need:

- **`python 3.9 - 3.13`** – `windows-curses` only ships pre-built wheels for these versions. if you got newer python and `pip install` fails with *"could not find a version that satisfies the requirement windows-curses"*, either downgrade python or use `--headless` mode (which does not need curses).
- **`windows-curses>=2.3.2`** – installed automatically by `pip install -e .`. if you install deps manually, run:
  ```powershell
  pip install "windows-curses>=2.3.2"
  ```
- **ffmpeg in your `PATH`**, easiest way to get it is:
  ```powershell
  # winget
  winget install --id Gyan.FFmpeg

  # or choco
  choco install ffmpeg

  # or scoop
  scoop install ffmpeg
  ```
  alternatively, download a static build from [ffmpeg.org](https://ffmpeg.org/download.html#build-windows)
  verify installation with:
  ```powershell
  ffmpeg -version
  ffprobe -version
  ```
---

## installation

```bash
git clone https://github.com/alperien/udemy-dl.git
cd udemy-dl
pipx install -e .
```

on windows:

```powershell
git clone https://github.com/alperien/udemy-dl.git
cd udemy-dl
pipx install -e .
# or, if you don't have pipx:
# pip install -e .
```

---

## getting your credentials

you need two values from your browser cookies after logging in to udemy:

1. open [udemy.com](https://www.udemy.com) and log in.
2. open *developer tools* (`F12`) → *application* tab → *cookies* → `https://www.udemy.com`.
3. copy:
   - `access_token` → your token
   - `client_id` → your client_id

---

## usage

```bash
udemy-dl
```

### headless mode

run without TUI:

```bash
# download all courses
UDEMY_TOKEN="..." UDEMY_CLIENT_ID="..." udemy-dl --headless

# download a specific one
udemy-dl --headless --course-id 12345

# set quality to 720p and skip extras
udemy-dl --headless --quality 720 --no-subtitles --no-materials
```

### shortcuts

| Key | Action |
|-----|--------|
| `j` / `↓` | move down |
| `k` / `↑` | move up |
| `Space` | toggle course selection |
| `Enter` | confirm / select |
| `q` / `Esc` | back / quit |
| `Ctrl+C` | abort download |

---

## configuration

config is in `~/.config/udemy-dl/config.json` (permissions: `600`).

on windows the default path is `C:\Users\<you>\.config\udemy-dl\config.json`.

## logs

logs are in `~/.config/udemy-dl/downloader.log`.

on windows: `C:\Users\<you>\.config\udemy-dl\downloader.log`.

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
