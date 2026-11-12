# mqtt-pi — Problem Set 2

A Raspberry Pi MQTT client for a Mosquitto broker. Each Pi belongs to one of
`melody`, `harmony`, or `rhythm`; this Pi defaults to `melody`.

## Setup on Raspberry Pi OS

Wire the LED with an appropriate series resistor and the passive buzzer using
hardware suitable for GPIO drive. Pins in config are BCM numbers, not physical
header positions. Defaults: LED GPIO17, passive buzzer GPIO18.

```sh
sudo apt update
sudo apt install mosquitto mosquitto-clients python3-venv python3-gpiozero python3-lgpio
sudo systemctl enable --now mosquitto
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r src/requirements.txt
python src/main.py
```

The local Mosquitto installation is for same-Pi testing. For the assignment demo,
set broker host, port and credentials to the class broker. Do not use localhost
for a broker running on another computer. This implementation uses plain MQTT;
if the class broker requires TLS, add TLS configuration before connecting.

## Files

- `src/config.json`: broker, node, sections, selected section, conductor, BCM pins,
  and topic templates. `sections` lists choices; `section` assigns this Pi one part.
- `src/main.py`: connects, subscribes, validates messages, stores a score, plays it
  on a worker thread, publishes status, and records rejections.
- `src/requirements.txt`: Paho MQTT client and GPIO Zero hardware dependencies.
- `src/test_commands.py`: manual demo helper invoking Mosquitto command-line tools;
  it reads the same configuration as the app and does not control GPIO.
- `tests/test_node.py`: automated hardware-free behavior checks using mocks.
- `src/mqtt-pi.log`: generated at runtime; application status and rejection records.

## Demo

Keep the app running. In a second terminal, activate the environment and run:

```sh
python src/test_commands.py watch
```

In a third terminal:

```sh
python src/test_commands.py score
python src/test_commands.py start --scope all
# Let playback finish, then repeat for the section and individual node:
python src/test_commands.py start --scope section
python src/test_commands.py stop --scope node
python src/test_commands.py start --scope node
python src/test_commands.py malformed
python src/test_commands.py unauthorized
```

Execute each START after the previous playback finishes or has been stopped.
The demo score contains five notes and one rest. Loading reports READY, starting
reports PLAYING, completion or interruption reports STOPPED, and rejections report
ERROR. Watch subscribes only to this Pi's status topic; start it before loading
the score to see READY. Commands and status are not retained.

## Shared message format (proposed version for class agreement)

All commands must be JSON objects containing a nonempty string `type`,
`performance_id`, and `sender`, plus an object `data`.

```json
{
  "type": "SCORE",
  "performance_id": "demo-001",
  "sender": "conductor-1",
  "data": {
    "tempo": 120,
    "notes": [
      {"frequency": 262, "beats": 1},
      {"frequency": 0, "beats": 1}
    ]
  }
}
```

`SCORE` stores a score without playing it. Tempo is 20–300 BPM. A score has
1–1000 entries. Frequency is 20–5000 Hz for a note or 0 for a rest; beats is
0.0625–16. Each entry lasts `beats * 60 / tempo` seconds. The demo helper sends
six entries; arbitrary scores need not contain five notes and a rest.

`START` and `STOP` use the same envelope with `data: {}`. Their performance ID
must match the loaded score. START while playing and SCORE while playing are
rejected. STOP interrupts the current wait and silences the outputs. Restarting
a completed or stopped performance plays it from the beginning.

| Topic | Accepted command types |
| --- | --- |
| `orchestra/all/control` | START, STOP |
| `orchestra/section/<section>/score` | SCORE |
| `orchestra/section/<section>/control` | START, STOP |
| `orchestra/node/<node>/control` | SCORE, START, STOP |
| `orchestra/status/<node>` | Outgoing STATUS |

Status includes `type: "STATUS"`, `performance_id` (null before a score), node
name as `sender`, and `data` containing `status`, `section`, and `detail`.

The configured conductor sender is checked for all commands, including score
selection. This is a temporary PS2 authorization rule, not conductor election or
cryptographic authentication. Broker credentials and ACLs are needed to prevent
sender impersonation. Agree on this proposed format before class integration;
document and coordinate subsequent changes. Composer UI and election are outside
this implementation.

## How main.py works

1. `main()` sets up terminal/file logging, loads configuration, and constructs
   `OrchestraNode`. `load_config()` rejects an unknown selected section.
2. The constructor expands topic templates and creates initially silent GPIO
   devices, cancellation event, and MQTT client with version 2 callbacks.
3. `run()` connects and runs the MQTT network loop. `on_connect()` subscribes to
   four command topics, including after reconnection. `on_subscribe()` reports
   READY only after the broker acknowledges subscriptions.
4. `validate()` checks exact topic, retained flag, payload size, UTF-8/JSON shape,
   required fields, permitted type, conductor sender and score data ranges.
5. `on_message()` stores an authorized score or checks the active performance ID
   before START/STOP. Invalid messages publish ERROR and log the reason plus up
   to 2048 payload bytes. No hardware action is taken for invalid commands.
6. START creates a playback thread. `play()` changes PWM frequency for each note,
   sets 50% duty cycle, and turns on the LED. Rests silence both outputs.
   `Event.wait(duration)` allows STOP to interrupt a note immediately rather than
   waiting for an ordinary sleep to finish. MQTT reception continues meanwhile.
7. STOP sets the event and joins the worker. Its finally block silences outputs
   and reports STOPPED (or ERROR on a playback failure). A disconnect also sets
   the cancellation event. Status cannot reach the broker while disconnected.
8. Ctrl+C triggers cleanup: cancel playback, join the worker, silence hardware,
   disconnect MQTT and close GPIO devices.

This is immediate playback, not precisely synchronized multi-Pi scheduling.
QoS 1 may redeliver commands; message-ID deduplication is not implemented.
READY on connection means the node is listening; READY with "Score loaded" means
it has a score. Scores live only in memory and disappear when the program exits.

## Automated checks

```sh
python3 -m unittest discover -s tests -v
```

These check validation and playback logic with simulated dependencies. Actual
broker connectivity, GPIO wiring, pitch and timing still need testing on the Pi.
