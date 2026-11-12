"""Hardware-free behavior checks; run with unittest discovery."""
import importlib.util
import json
from pathlib import Path
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
# Import the application without requiring Pi libraries on the development host.
with patch.dict(sys.modules, {name: MagicMock() for name in
                             ("paho", "paho.mqtt", "paho.mqtt.client", "gpiozero")}):
    spec = importlib.util.spec_from_file_location("pi_main", ROOT / "src/main.py")
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)


class NodeTests(unittest.TestCase):
    def setUp(self):
        config = json.loads((ROOT / "src/config.json").read_text())
        self.node = app.OrchestraNode(config)
        self.node.status = MagicMock()

    def message(self, kind="SCORE", **changes):
        command = {"type": kind, "performance_id": "test-1",
                   "sender": "conductor-1", "data": {}}
        if kind == "SCORE":
            command["data"] = {"tempo": 120, "notes": [
                {"frequency": 262, "beats": 1}, {"frequency": 0, "beats": 1}]}
        command.update(changes)
        return SimpleNamespace(topic=self.node.topics["node_control"],
                               payload=json.dumps(command).encode(), retain=False)

    def deliver(self, message):
        self.node.on_message(None, None, message)

    def test_score_loads_without_playing(self):
        self.deliver(self.message())
        self.assertEqual(self.node.performance_id, "test-1")
        self.assertIsNone(self.node.worker)
        self.node.status.assert_called_with("READY", "Score loaded")

    def test_rejects_unauthorized_score(self):
        self.deliver(self.message(sender="intruder"))
        self.assertIsNone(self.node.score)
        self.assertEqual(self.node.status.call_args.args[0], "ERROR")

    def test_rejects_malformed_json(self):
        message = self.message()
        message.payload = b"{broken"
        self.deliver(message)
        self.assertIsNone(self.node.score)
        self.assertEqual(self.node.status.call_args.args[0], "ERROR")

    def test_rejects_wrong_topic_type_and_retained(self):
        for topic, retain in [(self.node.topics["all_control"], False),
                              ("unrelated/topic", False),
                              (self.node.topics["node_control"], True)]:
            with self.subTest(topic=topic, retain=retain):
                message = self.message()
                message.topic, message.retain = topic, retain
                with self.assertRaises(ValueError):
                    self.node.validate(message)

    def test_rejects_invalid_note_values(self):
        for value in [True, -1, 10, float("nan"), float("inf"), "262"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.node.validate(self.message(data={"tempo": 120, "notes": [
                        {"frequency": value, "beats": 1}]}))

    def test_rejects_start_without_matching_score(self):
        self.deliver(self.message("START"))
        self.assertIsNone(self.node.worker)
        self.deliver(self.message())
        self.deliver(self.message("START", performance_id="different"))
        self.assertIsNone(self.node.worker)
        self.assertEqual(self.node.status.call_args.args[0], "ERROR")

    def test_notes_rests_and_duration(self):
        self.deliver(self.message())
        self.node.cancel = MagicMock()
        self.node.cancel.is_set.return_value = False
        self.node.cancel.wait.return_value = False
        self.node.led.reset_mock()
        self.node.play()
        self.node.led.on.assert_called_once()
        self.assertEqual(self.node.cancel.wait.call_count, 2)
        self.node.cancel.wait.assert_called_with(0.5)
        self.assertEqual(self.node.buzzer.value, 0)
        self.node.status.assert_called_with("STOPPED", "Score completed")

    def test_stop_interrupts_playback(self):
        self.deliver(self.message())
        self.node.score["notes"][0]["beats"] = 16
        started = threading.Event()
        self.node.status.side_effect = lambda state, detail: (
            started.set() if state == "PLAYING" else None)
        self.deliver(self.message("START"))
        self.assertTrue(started.wait(1))
        self.deliver(self.message("STOP"))
        self.assertFalse(self.node.worker.is_alive())
        self.assertEqual(self.node.buzzer.value, 0)
        self.node.status.assert_called_with("STOPPED", "Playback interrupted")


if __name__ == "__main__":
    unittest.main()
