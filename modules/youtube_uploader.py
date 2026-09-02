"""Stage 7: YouTube Auto-Uploader — YouTube Data API v3 with OAuth2, multi-channel support."""

import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import (
    YOUTUBE_CATEGORY_ID,
    YOUTUBE_CHANNEL_ID,
    YOUTUBE_CLIENT_SECRET,
    YOUTUBE_PRIVACY,
    YOUTUBE_SCOPES,
    YOUTUBE_TOKEN_FILE,
)
from modules.script_engine import Script

logger = logging.getLogger(__name__)

MAX_TAGS = 500


class YouTubeUploader:
    def __init__(self):
        self.service = self._auth()
        self._verify_channel()

    def _auth(self):
        creds = None
        token_file = Path(YOUTUBE_TOKEN_FILE)

        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), YOUTUBE_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not Path(YOUTUBE_CLIENT_SECRET).exists():
                    raise FileNotFoundError(
                        f"client_secret.json topilmadi: {YOUTUBE_CLIENT_SECRET}\n"
                        "Google Cloud Console → APIs & Services → Credentials dan yuklab oling."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    YOUTUBE_CLIENT_SECRET, YOUTUBE_SCOPES
                )
                creds = flow.run_local_server(port=0)
            token_file.write_text(creds.to_json())
            logger.info("Token saqlandi: %s", token_file)

        return build("youtube", "v3", credentials=creds)

    def list_channels(self) -> list[dict]:
        """Returns all YouTube channels the authenticated user manages."""
        resp = self.service.channels().list(
            part="snippet,id",
            mine=True,
            maxResults=50,
        ).execute()
        channels = []
        for item in resp.get("items", []):
            channels.append({
                "id": item["id"],
                "name": item["snippet"]["title"],
                "url": f"https://www.youtube.com/channel/{item['id']}",
            })
        return channels

    def _verify_channel(self):
        """If YOUTUBE_CHANNEL_ID is set, confirm it belongs to this account."""
        if not YOUTUBE_CHANNEL_ID:
            return
        channels = self.list_channels()
        ids = [c["id"] for c in channels]
        if YOUTUBE_CHANNEL_ID not in ids:
            names = "\n".join(f"  {c['id']} — {c['name']}" for c in channels)
            raise ValueError(
                f"YOUTUBE_CHANNEL_ID='{YOUTUBE_CHANNEL_ID}' bu accountda topilmadi.\n"
                f"Mavjud kanallar:\n{names}\n"
                "To'g'ri ID ni .env ga yozing."
            )
        ch = next(c for c in channels if c["id"] == YOUTUBE_CHANNEL_ID)
        logger.info("Kanal tasdiqlandi: %s (%s)", ch["name"], ch["id"])

    def _trim_tags(self, tags: list[str]) -> list[str]:
        result, total = [], 0
        for tag in tags:
            if total + len(tag) + 1 > MAX_TAGS:
                break
            result.append(tag)
            total += len(tag) + 1
        return result

    def upload(
        self,
        video_path: Path,
        script: Script,
        thumbnail_path: Path | None = None,
        privacy: str | None = None,
    ) -> dict:
        privacy = privacy or YOUTUBE_PRIVACY
        tags = self._trim_tags(script.tags)

        body = {
            "snippet": {
                "title": script.title,
                "description": script.description,
                "tags": tags,
                "categoryId": YOUTUBE_CATEGORY_ID,
                "defaultLanguage": "en",
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        # Target specific channel if configured (Brand Account)
        if YOUTUBE_CHANNEL_ID:
            body["snippet"]["channelId"] = YOUTUBE_CHANNEL_ID

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,
        )

        logger.info("Yuklanmoqda: '%s' [%s]...", script.title, privacy)
        request = self.service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                logger.info("Yuklash: %d%%", pct)

        video_id = response["id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info("Yuklandi: %s", video_url)

        if thumbnail_path and thumbnail_path.exists():
            try:
                self.service.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg"),
                ).execute()
                logger.info("Thumbnail qo'yildi.")
            except Exception as e:
                logger.warning("Thumbnail xatosi: %s", e)

        return {"id": video_id, "url": video_url}
