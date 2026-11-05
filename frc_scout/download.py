"""Download match VODs with yt-dlp."""
import subprocess
from pathlib import Path


def download(url: str, out_dir: Path, height: int = 720) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl = str(out_dir / "%(id)s.%(ext)s")
    fmt = f"bv*[height<={height}]+ba/b[height<={height}]/b"
    subprocess.run(
        ["yt-dlp", "-f", fmt, "--merge-output-format", "mp4",
         "--no-playlist", "-o", tmpl, url],
        check=True,
    )
    # find the merged file
    files = sorted(out_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    return files[-1]
