### Summary
This change includes several good improvements: fixing pagination URLs in the API, handling uncategorized lectures, preferring direct video files over HLS, stripping HTML tags from subtitles, and adding interruption support for material downloads. However, there are a couple of bugs introduced in the new ffmpeg output reading logic and the material download interruption handling.

### Issues Found
| Severity | File:Line | Issue |
|----------|-----------|-------|
| WARNING | [`src/udemy_dl/dl.py:127`](src/udemy_dl/dl.py:127) | Flawed logic for splitting ffmpeg output buffer |
| WARNING | [`src/udemy_dl/dl.py:242`](src/udemy_dl/dl.py:242) | Interrupted material downloads are treated as successful |

### Detailed Findings

**File:** [`src/udemy_dl/dl.py:127`](src/udemy_dl/dl.py:127)
- **Confidence:** 95%
- **Problem:** The logic `while "\r" in buffer or "\n" in buffer:` followed by `if "\r" in buffer:` splits on `\r` even if `\n` appears first in the buffer. For example, if the buffer is `"log\nprogress\r"`, it splits on `\r`, yielding `"log\nprogress"`. This breaks the line-by-line processing of ffmpeg output, which can cause the progress bar to skip updates or lag.
- **Suggestion:** Use `re.split` to split on any sequence of newlines/carriage returns, or find the first occurrence of either character.
  ```python
            buffer += chunk.decode("utf-8", "ignore")
            parts = re.split(r'[\r\n]+', buffer)
            buffer = parts.pop()
            for line in parts:
                if line.strip():
                    yield line.strip().lower()
  ```

**File:** [`src/udemy_dl/dl.py:242`](src/udemy_dl/dl.py:242)
- **Confidence:** 95%
- **Problem:** In `download_materials`, if `is_interrupted()` is true, it breaks the chunk loop. However, because some chunks were already written, `mat_path.stat().st_size > 0` is true. The code then appends the partially downloaded file to `downloaded` and logs it as successful.
- **Suggestion:** Check if the download was interrupted before appending to `downloaded`, and delete the partial file if it was.
  ```python
                    if is_interrupted and is_interrupted():
                        logger.warning(f"Material download interrupted: {filename}")
                        if mat_path.exists():
                            mat_path.unlink()
                    elif mat_path.exists() and mat_path.stat().st_size > 0:
                        downloaded.append(mat_path)
                        logger.info(f"Downloaded material: {filename}")
                    else:
                        logger.warning(f"Material file empty: {filename}")
                        if mat_path.exists():
                            mat_path.unlink()
  ```

### Recommendation
**APPROVE WITH SUGGESTIONS**
