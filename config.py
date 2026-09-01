import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET_FILE", str(BASE_DIR / "client_secret.json"))

# Paths
HISTORY_DIR = BASE_DIR / "history"
OUTPUT_DIR = BASE_DIR / "output"
ASSETS_DIR = BASE_DIR / "assets"
SFX_DIR = ASSETS_DIR / "sfx"
MUSIC_DIR = ASSETS_DIR / "music"
LOGS_DIR = BASE_DIR / "logs"
TOPIC_HISTORY_FILE = HISTORY_DIR / "topics.json"

# Script Engine
GEMINI_MODEL = "gemini-1.5-pro"
SCRIPT_LANGUAGE = os.getenv("SCRIPT_LANGUAGE", "English")
VIDEO_DURATION_TARGET = int(os.getenv("VIDEO_DURATION_TARGET", "300"))  # seconds

# TTS
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "edge")  # "edge" | "elevenlabs"
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "en-US-ChristopherNeural")

# Audio
MUSIC_VOLUME = float(os.getenv("MUSIC_VOLUME", "0.08"))
SFX_VOLUME = float(os.getenv("SFX_VOLUME", "0.5"))
NARRATOR_VOLUME = float(os.getenv("NARRATOR_VOLUME", "1.0"))

# Media
PEXELS_VIDEO_ORIENTATION = "landscape"
PEXELS_VIDEO_QUALITY = "hd"
PEXELS_PER_PAGE = 15
KEN_BURNS_ZOOM_RATIO = 0.04  # zoom-in factor per second

# Video
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
SUBTITLE_FONT = "Arial-Bold"
SUBTITLE_FONT_SIZE = 60
SUBTITLE_COLOR = "white"
SUBTITLE_STROKE_COLOR = "black"
SUBTITLE_STROKE_WIDTH = 3
SUBTITLE_POSITION = ("center", 0.80)

# YouTube Upload
YOUTUBE_CATEGORY_ID = "28"  # Science & Technology
YOUTUBE_PRIVACY = os.getenv("YOUTUBE_PRIVACY", "private")  # private | unlisted | public
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_TOKEN_FILE = BASE_DIR / "youtube_token.json"
