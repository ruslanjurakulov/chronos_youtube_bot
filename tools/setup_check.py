#!/usr/bin/env python3
"""Preflight check — tells you exactly what is still missing before a run.

  python tools/setup_check.py              # check everything, hide secret values
  python tools/setup_check.py --reveal     # also print the values to paste into
                                           # GitHub Secrets (your terminal only)

Exit code is 0 when local runs are possible, 1 when something required is missing.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OK, WARN, BAD = "OK  ", "WARN", "FAIL"


class Report:
    def __init__(self):
        self.rows: list[tuple[str, str, str]] = []
        self.blocking = 0

    def add(self, status: str, item: str, detail: str = ""):
        self.rows.append((status, item, detail))
        if status == BAD:
            self.blocking += 1

    def render(self):
        width = max(len(r[1]) for r in self.rows)
        for status, item, detail in self.rows:
            line = f"[{status}] {item.ljust(width)}"
            if detail:
                line += f"  {detail}"
            print(line)


def check_env(rep: Report):
    required = {
        "GEMINI_API_KEY": "Gemini — https://aistudio.google.com/apikey",
        "PEXELS_API_KEY": "Pexels — https://www.pexels.com/api/",
    }
    optional = {
        "YOUTUBE_CHANNEL_ID": "run: python main.py --list-channels",
        "ELEVENLABS_API_KEY": "only needed if TTS_PROVIDER=elevenlabs",
    }
    for key, hint in required.items():
        if os.getenv(key):
            rep.add(OK, key)
        else:
            rep.add(BAD, key, f"missing — {hint}")
    for key, hint in optional.items():
        rep.add(OK if os.getenv(key) else WARN, key, "" if os.getenv(key) else hint)


def check_files(rep: Report):
    secret = Path(os.getenv("YOUTUBE_CLIENT_SECRET_FILE", ROOT / "client_secret.json"))
    if not secret.is_absolute():
        secret = ROOT / secret
    if secret.exists():
        try:
            json.loads(secret.read_text())
            rep.add(OK, "client_secret.json")
        except json.JSONDecodeError:
            rep.add(BAD, "client_secret.json", "file is not valid JSON")
    else:
        rep.add(WARN, "client_secret.json", "needed only for YouTube upload")

    tokens = sorted(ROOT.glob("youtube_token*.json"))
    if tokens:
        rep.add(OK, "youtube_token.json", f"{len(tokens)} token file(s)")
    else:
        rep.add(WARN, "youtube_token.json", "created on first upload (OAuth)")


def check_ffmpeg(rep: Report):
    exe = shutil.which("ffmpeg")
    if not exe:
        rep.add(BAD, "ffmpeg", "not on PATH — audio/video stages will fail")
        return
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=10)
        rep.add(OK, "ffmpeg", out.stdout.splitlines()[0][:60])
    except (subprocess.SubprocessError, OSError) as exc:
        rep.add(BAD, "ffmpeg", f"found but not runnable: {exc}")


def check_imports(rep: Report):
    for mod, pkg in (
        ("google.genai", "google-genai"),
        ("edge_tts", "edge-tts"),
        ("whisper", "openai-whisper"),
        ("moviepy.editor", "moviepy==1.0.3"),
        ("pydub", "pydub"),
        ("PIL", "Pillow"),
        ("numpy", "numpy"),
    ):
        try:
            __import__(mod)
            rep.add(OK, mod)
        except ImportError as exc:
            rep.add(BAD, mod, f"pip install {pkg}  ({exc.msg})")


def check_assets(rep: Report):
    from tools.generate_assets import MUSIC, SFX

    for kind, table in (("sfx", SFX), ("music", MUSIC)):
        folder = ROOT / "assets" / kind
        have = sum(
            any((folder / f"{n}.{e}").exists() for e in ("mp3", "wav", "ogg"))
            for n in table
        )
        if have == len(table):
            rep.add(OK, f"assets/{kind}", f"{have}/{len(table)}")
        else:
            rep.add(WARN, f"assets/{kind}", f"{have}/{len(table)} — run: python tools/generate_assets.py")


def print_secrets(reveal: bool):
    """What to paste into GitHub → Settings → Secrets → Actions."""
    print("\n" + "=" * 70)
    print("GitHub Secrets (Settings -> Secrets and variables -> Actions)")
    print("=" * 70)

    entries: list[tuple[str, str | None]] = [
        ("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY")),
        ("PEXELS_API_KEY", os.getenv("PEXELS_API_KEY")),
        ("YOUTUBE_CHANNEL_ID", os.getenv("YOUTUBE_CHANNEL_ID")),
    ]
    for name, path in (
        ("YOUTUBE_CLIENT_SECRET_JSON", ROOT / "client_secret.json"),
        ("YOUTUBE_TOKEN_JSON", ROOT / "youtube_token.json"),
    ):
        entries.append((name, path.read_text().strip() if path.exists() else None))

    for name, value in entries:
        if value is None:
            print(f"\n{name}\n  (not available yet)")
        elif reveal:
            print(f"\n{name}\n{value}")
        else:
            shown = value[:6] + "..." if len(value) > 12 else "***"
            print(f"\n{name}\n  set, {len(value)} chars, starts {shown}")

    if not reveal:
        print("\nRe-run with --reveal to print the full values for copy-paste.")


def main():
    ap = argparse.ArgumentParser(description="Chronos setup preflight")
    ap.add_argument("--reveal", action="store_true",
                    help="print full secret values for pasting into GitHub Secrets")
    args = ap.parse_args()

    rep = Report()
    check_env(rep)
    check_files(rep)
    check_ffmpeg(rep)
    check_imports(rep)
    check_assets(rep)
    rep.render()

    print_secrets(args.reveal)

    print()
    if rep.blocking:
        print(f"{rep.blocking} blocking issue(s) — fix the FAIL rows above.")
        return 1
    print("Ready. Try: python main.py --niche \"history mysteries\" --no-upload")
    return 0


if __name__ == "__main__":
    sys.exit(main())
