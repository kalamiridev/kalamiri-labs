import json
import unittest

from homekit_mqtt.discovery import discovery_messages
from homekit_mqtt.mapping import build_devices

from .helpers import accessories

BASE = "client/c1/sl-gw-1"
PREFIX = "client/c1/ha"
BRIDGE = f"{BASE}/homekit-mqtt/availability"


def messages(fixture, index=0):
    device = build_devices("test", accessories(fixture), {})[index]
    return {topic: config for topic, config in discovery_messages(device, BASE, PREFIX, BRIDGE)}


class DiscoveryTest(unittest.TestCase):
    def test_thermostat_is_a_climate_entity(self):
        found = messages("ecobee_501")
        climate = found[f"{PREFIX}/climate/homekit_test_1/climate/config"]
        self.assertEqual(climate["modes"], ["off", "heat", "cool", "heat_cool"])
        self.assertEqual(climate["mode_command_topic"], f"{BASE}/My ecobee/set")
        self.assertEqual(climate["fan_modes"], ["on", "auto"])
        self.assertEqual(climate["min_temp"], 7.2)
        self.assertEqual(climate["max_temp"], 33.3)
        self.assertNotIn("state_topic", climate)
        # occupancy and motion are binary sensors; values in the climate are not repeated
        topics = sorted(found)
        self.assertIn(f"{PREFIX}/binary_sensor/homekit_test_1/occupancy/config", topics)
        self.assertNotIn(f"{PREFIX}/sensor/homekit_test_1/humidity/config", topics)

    def test_climate_mode_command_maps_heat_cool_to_auto(self):
        climate = messages("ecobee_501")[f"{PREFIX}/climate/homekit_test_1/climate/config"]
        self.assertIn('"heat_cool": "auto"', climate["mode_command_template"])

    def test_climate_temperature_uses_the_setpoint_of_the_mode(self):
        climate = messages("ecobee_501")[f"{PREFIX}/climate/homekit_test_1/climate/config"]
        self.assertIn("occupied_cooling_setpoint if value_json.system_mode == 'cool'", climate["temperature_state_template"])
        self.assertIn("occupied_heating_setpoint", climate["temperature_command_template"])

    def test_outlets_are_switches_with_json_payloads(self):
        found = messages("mss425f")
        switch = found[f"{PREFIX}/switch/homekit_test_1/switch_l2/config"]
        self.assertEqual(json.loads(switch["payload_on"]), {"state_l2": "ON"})
        self.assertEqual(switch["name"], "Switch 2")

    def test_alarm_panel(self):
        found = messages("aqara_gateway", index=1)
        (topic, config), = found.items()
        self.assertEqual(topic, f"{PREFIX}/alarm_control_panel/homekit_test_1_alarm1/alarm/config")
        self.assertIn('"ARM_AWAY": "armed_away"', config["command_template"])

    def test_every_entity_has_availability_and_unique_id(self):
        for fixture in ("ecobee_501", "schlage_sense", "velux_window_cover", "eve_degree", "haa_fan1"):
            for config in messages(fixture).values():
                self.assertEqual(config["availability"][1]["topic"], BRIDGE)
                self.assertTrue(config["unique_id"].startswith("homekit_test_1_"))
                json.dumps(config)


if __name__ == "__main__":
    unittest.main()
