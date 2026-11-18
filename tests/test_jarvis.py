"""Hardware-free tests for Jarvis: run with `python -m unittest discover tests`."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("JARVIS_MUTE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Jarvis"))
import jarvis  # noqa: E402


class RouteTest(unittest.TestCase):
    def test_english_commands(self):
        cases = {
            "what time is it": "time",
            "what's the date today": "date",
            "wikipedia albert einstein": "wikipedia",
            "play music believer": "music",
            "open youtube": "youtube",
            "open google": "google",
            "change your name": "rename",
            "take a screenshot": "screenshot",
            "tell me a joke": "joke",
            "shutdown": "shutdown",
            "restart the computer": "restart",
            "go offline": "exit",
        }
        for query, action in cases.items():
            with self.subTest(query=query):
                self.assertEqual(jarvis.route(query), action)

    def test_chinese_commands(self):
        cases = {
            "現在幾點": "time",
            "今天幾號": "date",
            "維基百科 愛因斯坦": "wikipedia",
            "播放音樂 周杰倫": "music",
            "打開 YouTube": "youtube",
            "講個笑話": "joke",
            "幫我截圖": "screenshot",
            "再見": "exit",
        }
        for query, action in cases.items():
            with self.subTest(query=query):
                self.assertEqual(jarvis.route(query), action)

    def test_no_false_substring_matches(self):
        # "sometimes" contains "time"; "update" contains "date".
        self.assertIsNone(jarvis.route("sometimes i wonder"))
        self.assertIsNone(jarvis.route("please update me"))

    def test_argument_commands_win_over_short_words(self):
        self.assertEqual(jarvis.route("wikipedia time travel"), "wikipedia")

    def test_unknown_goes_to_llm(self):
        self.assertIsNone(jarvis.route("how do turbochargers work"))

    def test_strip_keywords(self):
        self.assertEqual(jarvis.strip_keywords("Wikipedia Albert Einstein", "wikipedia"), "albert einstein")
        self.assertEqual(jarvis.strip_keywords("播放音樂 周杰倫", "music"), "周杰倫")


class VoiceTest(unittest.TestCase):
    def test_pick_voice_prefers_exact_language(self):
        voices = [
            SimpleNamespace(id="cn", languages=["zh_CN"]),
            SimpleNamespace(id="tw", languages=["zh_TW"]),
            SimpleNamespace(id="en", languages=[b"\x05en-us"]),
        ]
        self.assertEqual(jarvis.pick_voice(voices, "zh-TW").id, "tw")
        self.assertEqual(jarvis.pick_voice(voices, "en-US").id, "en")
        self.assertEqual(jarvis.pick_voice(voices, "zh-HK").id, "cn")
        self.assertIsNone(jarvis.pick_voice(voices, "ja-JP"))


class FeatureTest(unittest.TestCase):
    def test_llm_unavailable_returns_none(self):
        with mock.patch.object(jarvis, "OLLAMA_URL", "http://127.0.0.1:9"):
            self.assertIsNone(jarvis.ask_llm("hi", [], timeout=2))

    def test_power_is_disabled_by_default(self):
        with mock.patch.object(jarvis, "ALLOW_POWER", False), mock.patch("subprocess.run") as run, \
                mock.patch("os.system") as system:
            self.assertTrue(jarvis.handle("shutdown", [], text_mode=True))
            run.assert_not_called()
            system.assert_not_called()

    def test_power_needs_confirmation(self):
        with mock.patch.object(jarvis, "ALLOW_POWER", True), mock.patch("builtins.input", return_value="no"), \
                mock.patch("subprocess.run") as run, mock.patch("os.system") as system:
            self.assertTrue(jarvis.handle("restart", [], text_mode=True))
            run.assert_not_called()
            system.assert_not_called()

    def test_negative_chinese_answer_cancels(self):
        with mock.patch.object(jarvis, "ALLOW_POWER", True), mock.patch("builtins.input", return_value="不是"), \
                mock.patch("subprocess.run") as run, mock.patch("os.system") as system:
            self.assertTrue(jarvis.handle("關機", [], text_mode=True))
            run.assert_not_called()
            system.assert_not_called()

    def test_name_is_saved_in_data_dir(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(jarvis, "DATA_DIR", Path(d)):
            self.assertEqual(jarvis.load_name(), "Jarvis")
            jarvis.save_name("Friday")
            self.assertEqual(jarvis.load_name(), "Friday")

    def test_find_songs_searches_subfolders(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "Album").mkdir()
            (Path(d) / "Album" / "Believer.mp3").touch()
            (Path(d) / "notes.txt").touch()
            self.assertEqual([p.name for p in jarvis.find_songs(Path(d))], ["Believer.mp3"])
            self.assertEqual(jarvis.find_songs(Path(d), "nothing"), [])

    def test_exit_stops_loop(self):
        self.assertFalse(jarvis.handle("goodbye", [], text_mode=True))


if __name__ == "__main__":
    unittest.main()
