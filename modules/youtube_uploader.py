"""Stage 7: YouTube Auto-Uploader — YouTube Data API v3 with OAuth2."""

import logging
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import (
    YOUTUBE_CATEGORY_ID,
    YOUTUBE_CLIENT_SECRET,
    YOUTUBE_PRIVACY,
    YOUTUBE_SCOPES,
    YOUTUBE_TOKEN_FILE,
)
from modules.script_engine import Script

logger = logging.getLogger(__name__)

MAX_TAGS = 500  # YouTube tag character limit


class YouTubeUploader:
    def __init__(self):
        self.service = self._auth()

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
                        f"YouTube client_secret.json not found at {YOUTUBE_CLIENT_SECRET}. "
                        "Download it from Google Cloud Console → APIs & Services → Credentials."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    YOUTUBE_CLIENT_SECRET, YOUTUBE_SCOPES
                )
                creds = flow.run_local_server(port=0)
            token_file.write_text(creds.to_json())

        return build("youtube", "v3", credentials=creds)

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
    ) -> str:
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

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,  # 10 MB chunks
        )

        logger.info("Uploading '%s' as %s...", script.title, privacy)
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
                logger.info("Upload progress: %d%%", pct)

        video_id = response["id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info("Uploaded! %s", video_url)

        # Set thumbnail
        if thumbnail_path and thumbnail_path.exists():
            try:
                self.service.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg"),
                ).execute()
                logger.info("Thumbnail set.")
            except Exception as e:
                logger.warning("Thumbnail upload failed: %s", e)

        return video_url
