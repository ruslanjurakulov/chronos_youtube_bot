"""The narrator is checked before the run spends anything — and never substituted.

A channel set to ElevenLabs was set that way for the voice. With auto publish
on, nobody hears the result before the audience does, so narrating in a
different voice would put a video on YouTube that does not sound like the
channel. These tests pin the refusal to do that, and pin that the check is
cheap and early.
"""

import unittest
from unittest.mock import MagicMock, patch

from modules.audio_mixer import VoiceUnavailable, verify_voice


def channel(provider, voice_id="pNInz6obpgDQGcFmaJgB"):
    ctx = MagicMock()
    ctx.agent.tts_provider = provider
    ctx.agent.elevenlabs_voice_id = voice_id
    return ctx


class EdgeNeedsNothing(unittest.TestCase):
    @patch("modules.audio_mixer.requests.get")
    def test_an_edge_channel_is_not_checked_at_all(self, get):
        verify_voice(channel("edge"))
        get.assert_not_called()


class ElevenLabsMustBeUsable(unittest.TestCase):
    @patch("modules.audio_mixer.ELEVENLABS_API_KEY", "")
    @patch("modules.audio_mixer.requests.get")
    def test_a_missing_key_stops_the_run_before_any_request(self, get):
        """Run #20's failure: the secret was empty and nothing noticed until the
        audio stage, four Gemini calls later."""
        with self.assertRaises(VoiceUnavailable) as caught:
            verify_voice(channel("elevenlabs"))
        self.assertIn("ELEVENLABS_API_KEY", str(caught.exception))
        get.assert_not_called()

    @patch("modules.audio_mixer.ELEVENLABS_API_KEY", "k")
    @patch("modules.audio_mixer.requests.get")
    def test_a_missing_voice_id_stops_the_run(self, get):
        with self.assertRaises(VoiceUnavailable):
            verify_voice(channel("elevenlabs", voice_id=""))
        get.assert_not_called()

    @patch("modules.audio_mixer.ELEVENLABS_API_KEY", "k")
    @patch("modules.audio_mixer.requests.get")
    def test_an_unknown_voice_id_says_so(self, get):
        """'16516516145' is what a person types when guessing at an id."""
        get.return_value = MagicMock(status_code=404, json=lambda: {})
        with self.assertRaises(VoiceUnavailable) as caught:
            verify_voice(channel("elevenlabs", voice_id="16516516145"))
        self.assertIn("16516516145", str(caught.exception))

    @patch("modules.audio_mixer.ELEVENLABS_API_KEY", "k")
    @patch("modules.audio_mixer.requests.get")
    def test_it_quotes_elevenlabs_own_reason_for_a_401(self, get):
        """invalid_api_key and quota_exceeded share a status and need opposite fixes."""
        get.return_value = MagicMock(
            status_code=401,
            json=lambda: {"detail": {"status": "quota_exceeded"}},
        )
        with self.assertRaises(VoiceUnavailable) as caught:
            verify_voice(channel("elevenlabs"))
        self.assertIn("quota_exceeded", str(caught.exception))

    @patch("modules.audio_mixer.ELEVENLABS_API_KEY", "k")
    @patch("modules.audio_mixer.requests.get")
    def test_a_working_voice_passes_quietly(self, get):
        get.return_value = MagicMock(status_code=200, json=lambda: {"voice_id": "x"})
        verify_voice(channel("elevenlabs"))

    @patch("modules.audio_mixer.ELEVENLABS_API_KEY", "k")
    @patch("modules.audio_mixer.requests.get", side_effect=OSError("network down"))
    def test_an_outage_does_not_stop_the_run(self, _):
        """The real call happens a few stages later. A blip must not be the
        thing that kills a run before it starts."""
        verify_voice(channel("elevenlabs"))


class NoSubstitution(unittest.TestCase):
    @patch("modules.audio_mixer.ELEVENLABS_API_KEY", "")
    def test_it_raises_rather_than_returning_a_different_provider(self):
        """There is no return value that could be read as 'use edge instead'."""
        with self.assertRaises(VoiceUnavailable):
            verify_voice(channel("elevenlabs"))


if __name__ == "__main__":
    unittest.main()
