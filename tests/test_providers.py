"""Tests for modules/providers.py — the provider-interface seam.

Proves the Protocols are structural (a class with the right methods conforms,
one without doesn't), that the real research adapter conforms and delegates,
and that the existing MediaFetcher already satisfies the media protocols
without any change to it (the whole point of the seam)."""

import unittest
from pathlib import Path
from unittest.mock import patch

from modules.providers import (
    AnalyticsProvider,
    GeminiResearchProvider,
    ImageProvider,
    PublishingProvider,
    ResearchProvider,
    VideoProvider,
    VoiceProvider,
    research_provider,
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


if __name__ == "__main__":
    unittest.main()
