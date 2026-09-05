"""Stage 7: YouTube Auto-Uploader — YouTube Data API v3 with OAuth2.

Channel isolation (Phase 5)
---------------------------
An uploader instance is bound to exactly one channel for its whole life. Pass a
``ChannelContext`` and it authenticates with *that* channel's token and targets
*that* channel's YouTube id; pass nothing and it behaves precisely as the
single-channel uploader always has, reading ``config.py``.

The rule that matters is the negative one: a non-default channel NEVER falls
back to the ``YOUTUBE_CHANNEL_ID`` environment variable. Publishing Finance's
video to History's channel because a config field was blank would be worse than
failing, so a channel with no target of its own simply omits the field and
uploads to whatever channel its own token owns.

The publish gate is not implemented here and is not changed here: this module
uploads when it is called, exactly as before. Whether it *should* be called is
main.py's business, and main.py's behaviour is unchanged.
"""

import logging
from pathlib import Path
from typing import Optional

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
from modules.channels import ChannelContext
from modules.channel_credentials import (
    client_secret_problem,
    materialize_token,
    require_interactive_consent_possible,
    token_path,
)
from modules.script_engine import Script

logger = logging.getLogger(__name__)

MAX_TAGS = 500


class YouTubeUploader:
    def __init__(self, channel: Optional[ChannelContext] = None):
        self.channel = channel
        self.token_file = self._resolve_token_file(channel)
        self.target_channel_id = self._resolve_target_channel(channel)
        self.service = self._auth()
        self._verify_channel()

    # -- channel binding ---------------------------------------------------

    @staticmethod
    def _resolve_token_file(channel: Optional[ChannelContext]) -> Path:
        """Which token this uploader authenticates with.

        No channel = the legacy path from config. With a channel, its token is
        first materialized from its env var if one is set (the same
        secret-to-file step the workflow already does for the single channel),
        then read from that channel's own path.
        """
        if channel is None:
            return Path(YOUTUBE_TOKEN_FILE)
        materialize_token(channel)
        return token_path(channel)

    @staticmethod
    def _resolve_target_channel(channel: Optional[ChannelContext]) -> str:
        """Which YouTube channel the upload targets.

        A non-default channel uses ONLY its own configured id — never the
        process-wide YOUTUBE_CHANNEL_ID, which belongs to the default channel.
        An empty value means "don't set channelId", i.e. upload to the channel
        the token itself owns.
        """
        if channel is None:
            return YOUTUBE_CHANNEL_ID
        if channel.is_default:
            return channel.credential.youtube_channel_id or YOUTUBE_CHANNEL_ID
        return channel.credential.youtube_channel_id

    @property
    def _label(self) -> str:
        """Channel prefix for log lines and errors (brief §28)."""
        return f"[channel: {self.channel.channel_id}] " if self.channel else ""

    def _auth(self):
        creds = None
        token_file = Path(self.token_file)

        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), YOUTUBE_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Existence is not enough: the workflows write this file with
                # `echo '<secret>' > client_secret.json`, so an unset secret
                # leaves an EMPTY file behind. Handing that to InstalledAppFlow
                # produced the bare JSONDecodeError every scheduled poll has
                # actually been failing with.
                problem = client_secret_problem()
                if problem:
                    raise FileNotFoundError(f"{self._label}{problem}")
                # And on CI there is no browser to consent in, so say that
                # instead of blocking on run_local_server until the timeout.
                require_interactive_consent_possible(
                    self._label, token_file, YOUTUBE_SCOPES
                )
                flow = InstalledAppFlow.from_client_secrets_file(
                    YOUTUBE_CLIENT_SECRET, YOUTUBE_SCOPES
                )
                creds = flow.run_local_server(port=0)
            token_file.write_text(creds.to_json())
            logger.info("%sToken saqlandi: %s", self._label, token_file.name)

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
        """If a target channel is configured, confirm the token can reach it."""
        target = self.target_channel_id
        if not target:
            return
        channels = self.list_channels()
        ids = [c["id"] for c in channels]
        if target not in ids:
            names = "\n".join(f"  {c['id']} — {c['name']}" for c in channels)
            raise ValueError(
                f"{self._label}YouTube kanal ID='{target}' bu tokenda topilmadi.\n"
                f"Mavjud kanallar:\n{names}\n"
                "To'g'ri ID ni kanal sozlamasiga (yoki .env ga) yozing."
            )
        ch = next(c for c in channels if c["id"] == target)
        logger.info("%sKanal tasdiqlandi: %s (%s)", self._label, ch["name"], ch["id"])

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
        title_override: str | None = None,
        description_override: str | None = None,
    ) -> dict:
        """Upload one video.

        `title_override` ships the script's alternative title (the B arm of the
        A/B test). None keeps `script.title`, which is what every caller did
        before the experiment existed. `description_override` exists for the
        same reason on the description — a Short points at the long video it
        was cut from, which the script's own description cannot know about.
        """
        privacy = privacy or YOUTUBE_PRIVACY
        tags = self._trim_tags(script.tags)
        title = (title_override or script.title or "").strip() or script.title
        description = description_override if description_override is not None else script.description

        body = {
            "snippet": {
                "title": title,
                "description": description,
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
        if self.target_channel_id:
            body["snippet"]["channelId"] = self.target_channel_id

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,
        )

        logger.info("%sYuklanmoqda: '%s' [%s]...", self._label, title, privacy)
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
        logger.info("%sYuklandi: %s", self._label, video_url)

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
