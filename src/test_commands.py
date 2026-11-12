"""Manual integration helper: publish using Mosquitto, not GPIO or Paho."""
import argparse
import json
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["watch", "score", "start", "stop",
                                            "malformed", "unauthorized"])
    parser.add_argument("--scope", choices=["all", "section", "node"], default="node")
    parser.add_argument("--performance", default="demo-001")
    args = parser.parse_args()
    config = json.loads((BASE / "config.json").read_text())
    topics = {key: value.format(**config) for key, value in config["topics"].items()}
    broker = config["broker"]
    tool = "mosquitto_sub" if args.action == "watch" else "mosquitto_pub"
    command = [tool, "-h", broker["host"], "-p", str(broker["port"])]
    if broker.get("username"):
        command += ["-u", broker["username"], "-P", broker.get("password", "")]
    if args.action == "watch":
        command += ["-t", topics["status"], "-v"]
    else:
        topic = topics[f"{args.scope}_control"]
        payload = {"type": args.action.upper(),
                   "performance_id": args.performance,
                   "sender": config["conductor"], "data": {}}
        if args.action == "score":
            topic = topics["section_score"]
            payload["data"] = {
                "tempo": 120,
                "notes": [{"frequency": frequency, "beats": 1}
                          for frequency in [262, 294, 330, 0, 349, 392]],
            }
        if args.action == "unauthorized":
            payload.update(type="START", sender="unauthorized-node")
        body = "{broken" if args.action == "malformed" else json.dumps(payload)
        command += ["-q", "1", "-t", topic, "-m", body]
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError:
        parser.exit(1, "Install mosquitto-clients first.\n")
    except subprocess.CalledProcessError as error:
        parser.exit(error.returncode, "Mosquitto command failed.\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
