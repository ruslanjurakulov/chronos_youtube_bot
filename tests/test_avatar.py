"""Tests for modules/avatar.py — the AITuber presenter layer.

The load-bearing guarantees: the synthetic-only safety guard actually refuses
real/identifiable people (in code, not prose), an unconfigured provider fails
loudly rather than shipping a blank presenter, and the guard runs before any
network call."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.avatar import (
    AvatarConfig,
    AvatarProvider,
    AvatarUnavailable,
    HiggsfieldAvatarProvider,
    UnsafeAvatarRequest,
    avatar_provider,
    synthetic_only_guard,
)

_ENV_KEYS = ("HIGGSFIELD_API_KEY", "HIGGSFIELD_API_BASE", "HIGGSFIELD_AVATAR_ENDPOINT")


class SyntheticOnlyGuardTestCase(unittest.TestCase):
    def test_allows_synthetic_character(self):
        # A described, invented character is fine — no exception.
        synthetic_only_guard("a stylized cartoon owl narrator, neon purple", "history mysteries")
        synthetic_only_guard(None, "a friendly 3D robot host")

    def test_refuses_real_person_markers(self):
        for ref in [
            "a photo of my friend John",
            "deepfake of a famous actor",
            "clone this celebrity's face",
            "the current president",
            "lookalike of a popular singer",
        ]:
            with self.assertRaises(UnsafeAvatarRequest):
                synthetic_only_guard(ref, "")

    def test_refuses_image_url_reference(self):
        with self.assertRaises(UnsafeAvatarRequest):
            synthetic_only_guard("https://example.com/someone.jpg", "")


class AvatarConfigTestCase(unittest.TestCase):
    def test_off_by_default(self):
        self.assertFalse(AvatarConfig.from_mapping(None).enabled)
        self.assertFalse(AvatarConfig.from_mapping({}).enabled)

    def test_parses_fields(self):
        cfg = AvatarConfig.from_mapping({
            "enabled": True, "provider": "higgsfield",
            "character_prompt": "a cartoon fox", "character_ref": "fox-v1",
        })
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.character_prompt, "a cartoon fox")


class ProviderFactoryTestCase(unittest.TestCase):
    def test_none_when_disabled(self):
        self.assertIsNone(avatar_provider(AvatarConfig(enabled=False)))

    def test_higgsfield_when_enabled(self):
        p = avatar_provider(AvatarConfig(enabled=True, provider="higgsfield"))
        self.assertIsInstance(p, HiggsfieldAvatarProvider)
        self.assertIsInstance(p, AvatarProvider)  # conforms to the protocol

    def test_unknown_provider_raises(self):
        with self.assertRaises(AvatarUnavailable):
            avatar_provider(AvatarConfig(enabled=True, provider="nope"))


class HiggsfieldProviderTestCase(unittest.TestCase):
    def setUp(self):
        # Ensure a clean, unconfigured environment for these tests.
        self._patcher = patch.dict(os.environ, {k: "" for k in _ENV_KEYS}, clear=False)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_unconfigured_raises_avatar_unavailable(self):
        with self.assertRaises(AvatarUnavailable):
            HiggsfieldAvatarProvider().generate("a cartoon owl", "owl-v1", Path("/tmp/x.mp4"))

    def test_guard_runs_before_config_check(self):
        # An unsafe request must be refused even before we look at credentials.
        with self.assertRaises(UnsafeAvatarRequest):
            HiggsfieldAvatarProvider().generate("host", "deepfake of a celebrity", Path("/tmp/x.mp4"))

    def test_submit_poll_happy_path(self):
        class FakeResp:
            def __init__(self, payload):
                self._payload = payload
                self.content = b"x"

            def raise_for_status(self):
                pass

            def json(self):
                return self._payload

        env = {
            "HIGGSFIELD_API_KEY": "k", "HIGGSFIELD_API_BASE": "https://api.example/v1",
            "HIGGSFIELD_AVATAR_ENDPOINT": "avatar/generate",
        }
        with patch.dict(os.environ, env, clear=False), \
             patch("requests.post", return_value=FakeResp({"id": "job-1"})) as post, \
             patch("requests.get", return_value=FakeResp({"status": "completed", "url": "https://x/v.mp4"})) as get, \
             patch.object(HiggsfieldAvatarProvider, "_download", return_value=Path("/tmp/out.mp4")) as dl:
            out = HiggsfieldAvatarProvider(poll_interval=0).generate("a cartoon owl", "owl-v1", Path("/tmp/out.mp4"))
        self.assertEqual(out, Path("/tmp/out.mp4"))
        post.assert_called_once()
        get.assert_called()
        dl.assert_called_once()


if __name__ == "__main__":
    unittest.main()
