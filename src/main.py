"""Problem Set 2 Raspberry Pi client for a Mosquitto MQTT broker."""

import json
import logging
import math
import threading
from pathlib import Path

import paho.mqtt.client as mqtt
from gpiozero import LED, PWMOutputDevice

BASE = Path(__file__).resolve().parent
log = logging.getLogger("mqtt-pi")


def number(value, minimum, maximum, name):
    """Reject booleans, non-finite numbers, and values outside safe limits."""
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"Invalid {name}: expected {minimum}–{maximum}")
    return value


def load_config():
    config = json.loads((BASE / "config.json").read_text())
    if config["section"] not in config["sections"]:
        raise ValueError("section must be one of the configured sections")
    for name in (config["node"], config["section"]):
        if not isinstance(name, str) or not name or any(c in name for c in "/+#"):
            raise ValueError("Node and section must be single MQTT topic levels")
    return config


class OrchestraNode:
    def __init__(self, config):
        self.config = config
        self.topics = {
            key: template.format(node=config["node"], section=config["section"])
            for key, template in config["topics"].items()
        }
        self.allowed = {
            self.topics["all_control"]: {"START", "STOP"},
            self.topics["section_score"]: {"SCORE"},
            self.topics["section_control"]: {"START", "STOP"},
            self.topics["node_control"]: {"SCORE", "START", "STOP"},
        }
        self.performance_id = None
        self.score = None
        self.worker = None
        self.cancel = threading.Event()
        self.led = LED(config["gpio"]["led"])
        self.buzzer = PWMOutputDevice(
            config["gpio"]["buzzer"],
            frequency=440,
            initial_value=0,
        )
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=config["node"],
        )
        broker = config["broker"]
        if broker.get("username"):
            self.client.username_pw_set(broker["username"], broker.get("password"))
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

    def status(self, state, detail=""):
        payload = {
            "type": "STATUS",
            "performance_id": self.performance_id,
            "sender": self.config["node"],
            "data": {"status": state, "section": self.config["section"],
                     "detail": detail},
        }
        log.info("Status: %s", payload)
        self.client.publish(self.topics["status"], json.dumps(payload),
                            qos=1, retain=False)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("Broker rejected connection: %s", reason_code)
            return
        # Subscribe again after every reconnect.
        client.subscribe([(topic, 1) for topic in self.allowed])

    def on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if any(code.is_failure for code in reason_codes):
            self.status("ERROR", "A required subscription was rejected")
        else:
            self.status("READY", "Subscribed; load a score before START")

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.cancel.set()
        log.warning("Disconnected: %s", reason_code)

    def validate(self, message):
        if message.topic not in self.allowed:
            raise ValueError("Unexpected topic")
        if message.retain:
            raise ValueError("Retained commands are not accepted")
        if len(message.payload) > 65536:
            raise ValueError("Message exceeds 64 KiB")
        command = json.loads(message.payload.decode("utf-8"))
        if not isinstance(command, dict):
            raise ValueError("Command must be a JSON object")
        for key in ("type", "performance_id", "sender"):
            if not isinstance(command.get(key), str) or not command[key].strip():
                raise ValueError(f"Missing or invalid {key}")
        if command["type"] not in self.allowed[message.topic]:
            raise ValueError("Message type is invalid for this topic")
        if command["sender"] != self.config["conductor"]:
            raise ValueError("Sender is not the configured conductor")
        data = command.get("data")
        if not isinstance(data, dict):
            raise ValueError("data must be an object")
        if command["type"] == "SCORE":
            number(data.get("tempo"), 20, 300, "tempo")
            notes = data.get("notes")
            if not isinstance(notes, list) or not 1 <= len(notes) <= 1000:
                raise ValueError("notes must contain 1–1000 entries")
            for note in notes:
                if not isinstance(note, dict):
                    raise ValueError("Each note must be an object")
                frequency = number(note.get("frequency"), 0, 5000, "frequency")
                if 0 < frequency < 20:
                    raise ValueError("Use 0 for a rest or 20–5000 Hz")
                number(note.get("beats"), 0.0625, 16, "beats")
        return command

    def on_message(self, client, userdata, message):
        try:
            command = self.validate(message)
            kind = command["type"]
            performance_id = command["performance_id"]
            playing = self.worker is not None and self.worker.is_alive()
            if kind == "SCORE":
                if playing:
                    raise ValueError("Cannot replace score during playback")
                self.performance_id = performance_id
                self.score = command["data"]
                self.status("READY", "Score loaded")
            else:
                if self.score is None:
                    raise ValueError("No score loaded")
                if performance_id != self.performance_id:
                    raise ValueError("Performance identifier does not match")
                if kind == "START":
                    if playing:
                        raise ValueError("Already playing")
                    self.cancel.clear()
                    self.worker = threading.Thread(target=self.play, daemon=True)
                    self.worker.start()
                else:
                    self.cancel.set()
                    if self.worker:
                        self.worker.join()
                    if not playing:
                        self.status("STOPPED", "Stop received while idle")
        except (ValueError, UnicodeError, RecursionError) as error:
            log.warning("Rejected topic=%r payload=%r reason=%s",
                        message.topic, message.payload[:2048], error)
            self.status("ERROR", str(error))

    def silence(self):
        self.buzzer.value = 0
        self.led.off()

    def play(self):
        state, detail = "STOPPED", "Score completed"
        try:
            self.status("PLAYING", "Playback started")
            seconds_per_beat = 60 / self.score["tempo"]
            for note in self.score["notes"]:
                if self.cancel.is_set():
                    break
                self.silence()
                if note["frequency"]:
                    self.buzzer.frequency = note["frequency"]
                    self.buzzer.value = 0.5
                    self.led.on()
                if self.cancel.wait(note["beats"] * seconds_per_beat):
                    break
            if self.cancel.is_set():
                detail = "Playback interrupted"
        except Exception:
            log.exception("Playback failed")
            state, detail = "ERROR", "Hardware playback failed"
        finally:
            self.silence()
            self.status(state, detail)

    def run(self):
        broker = self.config["broker"]
        try:
            self.client.connect(broker["host"], broker["port"], keepalive=60)
            self.client.loop_forever()
        finally:
            self.cancel.set()
            if self.worker:
                self.worker.join()
            self.silence()
            self.client.disconnect()
            self.buzzer.close()
            self.led.close()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(BASE / "mqtt-pi.log"),
                  logging.StreamHandler()],
    )
    try:
        OrchestraNode(load_config()).run()
    except KeyboardInterrupt:
        log.info("Application stopped")


if __name__ == "__main__":
    main()
