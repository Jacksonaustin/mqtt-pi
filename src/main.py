import json
import logging 
import math
import threading 
from pathlib import path

import paho.mqtt.client as mqtt
from gpiozero import LED, PWMOutputDevice 

BASE = Path(__file__).resolve().parent 

logging.basicConfig(
        level=logging.INFO
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(BASE / "mqtt-pi.log"),
            logging.StreamHandler(),
        ],
    )
    log = logging.getLogger("mqtt-pi")

    def number(valve, minimum, maximum, name):
        if(
                type(valve) not in (int, float)
                or not math.isfinite(valve)
                or not minium <= value <= maxium
            ):
                raise valvueError(f"Invalid {name}")
            return value



    class OrchestraNode:
        def __init__(self, config):
            self.config = config
            self.topics = {
                    key: value.format(
                        node=config["node"],
                        section=config["section"],
                        )
                    for key, value in config["topics"].items()
                }

            self.allowed = {
                    self.topics["all_control"]: {"START", "STOP"},
                    self.topics["section_score"]: {"SCORE"}
                    self.topics["section_control"]: {"START", "STOP"},
                    self.topics["node_control"]: {"SCORE", "START", "STOP"},
                    
                }
            self.peformance_id 
