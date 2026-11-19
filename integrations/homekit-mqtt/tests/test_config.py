import json
import tempfile
import unittest
from pathlib import Path

from homekit_mqtt import config as settings


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = {"MQTT_HOST": "broker", "HOMEKIT_DATA_DIR": self.dir.name}

    def tearDown(self):
        self.dir.cleanup()

    def test_defaults(self):
        cfg = settings.load(self.env)
        self.assertEqual(cfg.mqtt_port, 1883)
        self.assertEqual(cfg.base_topic, "homekit")
        self.assertEqual(cfg.discovery_prefix, "homeassistant")
        self.assertEqual(cfg.bridge_availability_topic, "homekit/homekit-mqtt/availability")
        self.assertEqual(cfg.pairing_file, Path(self.dir.name) / "pairing.json")
        self.assertEqual(cfg.devices, {})

    def test_host_is_required(self):
        with self.assertRaises(settings.ConfigError):
            settings.load({"HOMEKIT_DATA_DIR": self.dir.name})

    def test_wildcards_are_refused(self):
        with self.assertRaises(settings.ConfigError):
            settings.load({**self.env, "MQTT_BASE_TOPIC": "client/+/gw"})

    def test_password_needs_user(self):
        with self.assertRaises(settings.ConfigError):
            settings.load({**self.env, "MQTT_PASSWORD": "secret"})

    def test_devices_file(self):
        (Path(self.dir.name) / "devices.json").write_text(
            json.dumps(
                {
                    "My ecobee": {
                        "name": "Living Room Thermostat",
                        "limits": {"occupied_heating_setpoint": [18, 24]},
                        "exclude": ["target_humidity"],
                    }
                }
            ),
            encoding="utf-8",
        )
        options = settings.load(self.env).devices["My ecobee"]
        self.assertEqual(options.name, "Living Room Thermostat")
        self.assertEqual(options.limits, {"occupied_heating_setpoint": (18.0, 24.0)})
        self.assertEqual(options.exclude, frozenset({"target_humidity"}))

    def test_devices_file_errors(self):
        path = Path(self.dir.name) / "devices.json"
        for content in (
            "[]",
            json.dumps({"x": {"name": "a/b"}}),
            json.dumps({"x": {"limits": {"y": [5, 1]}}}),
            json.dumps({"x": {"colour": "red"}}),
            json.dumps({"x": {"exclude": "humidity"}}),
        ):
            path.write_text(content, encoding="utf-8")
            with self.assertRaises(settings.ConfigError, msg=content):
                settings.load(self.env)


if __name__ == "__main__":
    unittest.main()
