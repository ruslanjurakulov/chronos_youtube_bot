"""Tests for modules/providers.py — the provider-interface seam.

Proves the Protocols are structural (a class with the right methods conforms,
one without doesn't), that the real research adapter conforms and delegates,
and that the existing MediaFetcher already satisfies the media protocols
without any change to it (the whole point of the seam)."""

import unittest
from pathlib import Path
from unittest.mock import patch

from modules.providers import (
    AnalyticsClientAnalyticsProvider,
    AnalyticsProvider,
    AudioMixerVoiceProvider,
    GeminiResearchProvider,
    ImageProvider,
    PublishingProvider,
    ResearchProvider,
    VideoProvider,
    VoiceProvider,
    YouTubeUploaderPublishingProvider,
    analytics_provider,
    publishing_provider,
    research_provider,
    voice_provider,
)


class ProtocolsAreStructuralTestCase(unittest.TestCase):
    def test_conforming_object_matches(self):
        class Fake:
            def fetch_images(self, keywords, count=8):
                return []

            def fetch_videos(self, keywords, count=10):
                return []

        f = Fake()
        self.assertIsInstance(f, ImageProvider)
        self.assertIsInstance(f, VideoProvider)

    def test_non_conforming_object_does_not_match(self):
        class Empty:
            pass

        self.assertNotIsInstance(Empty(), ImageProvider)
        self.assertNotIsInstance(Empty(), ResearchProvider)

    def test_all_contracts_are_runtime_checkable(self):
        # Each should support isinstance() checks (i.e. be @runtime_checkable):
        # the call must return a bool and not raise "Instance and class checks
        # can only be used with @runtime_checkable protocols".
        for proto in (
            ResearchProvider, ImageProvider, VideoProvider,
            VoiceProvider, PublishingProvider, AnalyticsProvider,
        ):
            self.assertFalse(isinstance(object(), proto))


class GeminiResearchProviderTestCase(unittest.TestCase):
    def test_conforms_to_protocol(self):
        self.assertIsInstance(GeminiResearchProvider(), ResearchProvider)
        self.assertIsInstance(research_provider(), ResearchProvider)

    def test_delegates_to_research_topic(self):
        sentinel = object()
        with patch("modules.research_engine.research_topic", return_value=sentinel) as rt:
            result = GeminiResearchProvider().research("The Fall of Rome", "history")
        rt.assert_called_once_with("The Fall of Rome", "history")
        self.assertIs(result, sentinel)


class MediaFetcherSatisfiesMediaProtocolsTestCase(unittest.TestCase):
    """The existing MediaFetcher must satisfy the media protocols with NO change
    to it — that is what makes the seam additive."""

    def test_mediafetcher_is_image_and_video_provider(self):
        from modules.media_fetcher import MediaFetcher

        fetcher = MediaFetcher("test-slug")
        self.assertIsInstance(fetcher, ImageProvider)
        self.assertIsInstance(fetcher, VideoProvider)


class ConcreteAdaptersTestCase(unittest.TestCase):
    """The voice/publishing/analytics adapters conform to their protocols and
    delegate faithfully to the wrapped module — tested with injected fakes, so
    no edge_tts / pydub / Google client is imported."""

    def test_voice_adapter_conforms_and_delegates(self):
        class FakeMixer:
            def __init__(self):
                self.calls = []

            def synthesize_text(self, text, out_path, voice_role="main"):
                self.calls.append((text, Path(out_path), voice_role))
                return out_path

        fake = FakeMixer()
        provider = AudioMixerVoiceProvider(fake)
        self.assertIsInstance(provider, VoiceProvider)
        out = provider.synthesize("hello world", Path("/tmp/v.mp3"))
        self.assertEqual(out, Path("/tmp/v.mp3"))
        self.assertEqual(fake.calls[0][0], "hello world")
        self.assertEqual(fake.calls[0][2], "main")

    def test_publishing_adapter_conforms_and_passes_kwargs(self):
        class FakeUploader:
            def __init__(self):
                self.calls = []

            def upload(self, video_path, script, **kwargs):
                self.calls.append((Path(video_path), script, kwargs))
                return {"id": "vid-1"}

        fake = FakeUploader()
        provider = YouTubeUploaderPublishingProvider(fake)
        self.assertIsInstance(provider, PublishingProvider)
        script = object()
        result = provider.upload(Path("/tmp/final.mp4"), script, privacy="private", title_override="B title")
        self.assertEqual(result, {"id": "vid-1"})
        # kwargs flow through untouched — nothing the uploader can do is hidden.
        self.assertEqual(fake.calls[0][2], {"privacy": "private", "title_override": "B title"})

    def test_analytics_adapter_conforms_and_preserves_empty(self):
        class FakeClient:
            def __init__(self, ret):
                self.ret = ret
                self.calls = []

            def video_performance(self, video_id, start_date, end_date):
                self.calls.append((video_id, start_date, end_date))
                return self.ret

        # A real metric passes through.
        fake = FakeClient({"views": 1234})
        provider = AnalyticsClientAnalyticsProvider(fake, lookback_days=7)
        self.assertIsInstance(provider, AnalyticsProvider)
        self.assertEqual(provider.fetch_metrics("vid-1"), {"views": 1234})
        # A date window was computed and passed (start < end, ISO dates).
        vid, start, end = fake.calls[0]
        self.assertEqual(vid, "vid-1")
        self.assertLess(start, end)

        # An absent metric stays absent — never fabricated as a zero.
        empty = AnalyticsClientAnalyticsProvider(FakeClient({}))
        self.assertEqual(empty.fetch_metrics("vid-2"), {})

    def test_factories_return_conforming_providers(self):
        # Factories build without importing the heavy modules (construction is
        # lazy), and what they return conforms to the right protocol.
        self.assertIsInstance(voice_provider(), VoiceProvider)
        self.assertIsInstance(publishing_provider(), PublishingProvider)
        self.assertIsInstance(analytics_provider(), AnalyticsProvider)


if __name__ == "__main__":
    unittest.main()
