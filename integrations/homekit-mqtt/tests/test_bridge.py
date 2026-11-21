import asyncio
import json
import tempfile
import unittest

from aiohomekit.model.characteristics import CharacteristicsTypes
from aiohomekit.testing import FakeController

from homekit_mqtt import config as settings
from homekit_mqtt.bridge import Bridge

from .helpers import accessories

BASE = "client/c1/sl-gw-1"


class FakePublisher:
    def __init__(self):
        self.messages = []
        self.watched = []

    async def publish(self, topic, payload, retain=True):
        self.messages.append((topic, json.loads(payload) if payload else None, retain))

    async def watch(self, topic):
        self.watched.append(topic)

    def last(self, topic):
        for found, payload, _retain in reversed(self.messages):
            if found == topic:
                return payload
        raise AssertionError(f"nothing published to {topic}")

    def topics(self):
        return [topic for topic, _payload, _retain in self.messages]


def remember_writes(pairing):
    """A real accessory reports the written value when read; the fake needs help."""
    original = pairing.put_characteristics

    async def put(characteristics):
        results = await original(characteristics)
        for aid, iid, value in characteristics:
            if (aid, iid) not in results:
                pairing.accessories.aid(aid).characteristics.iid(iid).value = value
        return results

    pairing.put_characteristics = put


class BridgeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dir = tempfile.TemporaryDirectory()
        cfg = settings.load(
            {
                "MQTT_HOST": "broker",
                "HOMEKIT_DATA_DIR": self.dir.name,
                "MQTT_BASE_TOPIC": BASE,
                "HA_DISCOVERY_PREFIX": "client/c1/ha",
            }
        )
        self.controller = FakeController()
        self.pairing = await self.controller.add_paired_device(accessories("ecobee_501"), "ecobee")
        remember_writes(self.pairing)
        self.bridge = Bridge(cfg, self.controller)
        self.publisher = FakePublisher()
        self.bridge.publisher = self.publisher
        await self.bridge.add_pairing("ecobee", self.pairing)
        await self.bridge.flush()

    async def asyncTearDown(self):
        self.bridge.close()
        self.dir.cleanup()

    async def test_state_availability_and_discovery_are_published(self):
        message = self.publisher.last(f"{BASE}/My ecobee")
        self.assertEqual(message["system_mode"], "auto")
        self.assertIn("last_seen", message)
        self.assertEqual(self.publisher.last(f"{BASE}/My ecobee/availability"), {"state": "online"})
        self.assertIn("client/c1/ha/climate/homekit_ecobee_1/climate/config", self.publisher.topics())
        self.assertTrue(all(retain for _t, _p, retain in self.publisher.messages))

    async def test_command_sets_mode_then_setpoint_and_answers(self):
        await self.bridge.handle_command(
            "My ecobee", json.dumps({"system_mode": "heat", "occupied_heating_setpoint": 21.5})
        )
        message = self.publisher.last(f"{BASE}/My ecobee")
        self.assertEqual(message["system_mode"], "heat")
        self.assertEqual(message["occupied_heating_setpoint"], 21.5)
        self.assertEqual(message["occupied_cooling_setpoint"], 21.5)

    async def test_command_without_change_still_answers(self):
        before = len(self.publisher.messages)
        await self.bridge.handle_command("My ecobee", json.dumps({"system_mode": "auto"}))
        self.assertGreater(len(self.publisher.messages), before)
        self.assertEqual(self.publisher.last(f"{BASE}/My ecobee")["system_mode"], "auto")

    async def test_refused_value_changes_nothing(self):
        await self.bridge.handle_command("My ecobee", json.dumps({"occupied_cooling_setpoint": 40}))
        self.assertEqual(self.publisher.last(f"{BASE}/My ecobee")["occupied_cooling_setpoint"], 25.6)

    async def test_event_updates_state(self):
        char = self.pairing.accessories.aid(1).characteristics.iid(19)
        self.assertEqual(char.type, CharacteristicsTypes.TEMPERATURE_CURRENT)
        self.pairing.testing.update_aid_iid([(1, 19, 19.5)])
        await asyncio.sleep(0)
        await self.bridge.flush()
        self.assertEqual(self.publisher.last(f"{BASE}/My ecobee")["local_temperature"], 19.5)

    async def test_unreachable_accessory_goes_offline(self):
        self.pairing.available = False
        await self.bridge.poll("ecobee")
        await self.bridge.flush()
        self.assertEqual(self.publisher.last(f"{BASE}/My ecobee/availability"), {"state": "offline"})
        self.pairing.available = True
        await self.bridge.poll("ecobee")
        await self.bridge.flush()
        self.assertEqual(self.publisher.last(f"{BASE}/My ecobee/availability"), {"state": "online"})

    async def test_bad_commands_are_ignored(self):
        before = len(self.publisher.messages)
        await self.bridge.handle_command("Nobody", "{}")
        await self.bridge.handle_command("My ecobee", "not json")
        await self.bridge.handle_command("My ecobee", "[]")
        self.assertEqual(len(self.publisher.messages), before)

    async def test_a_name_another_device_has_leaves_the_device_out(self):
        catalog = f"{BASE}/bridge/devices"
        self.bridge.taken.apply(catalog, json.dumps([{"friendly_name": "My ecobee", "ieee_address": "0x01"}]))
        with self.assertLogs("homekit_mqtt.bridge", "ERROR"):
            self.bridge.apply_names()
        before = len(self.publisher.messages)
        await self.bridge.flush()
        published = self.publisher.messages[before:]
        self.assertNotIn(f"{BASE}/My ecobee", [topic for topic, _payload, _retain in published])
        self.assertIsNone(self.publisher.last("client/c1/ha/climate/homekit_ecobee_1/climate/config"))
        before = len(self.publisher.messages)
        await self.bridge.handle_command("My ecobee", json.dumps({"system_mode": "heat"}))
        self.assertEqual(len(self.publisher.messages), before)

        self.bridge.taken.apply(catalog, json.dumps([{"friendly_name": "Hall Plug", "ieee_address": "0x01"}]))
        self.bridge.apply_names()
        await self.bridge.flush()
        self.assertEqual(self.publisher.last(f"{BASE}/My ecobee")["system_mode"], "auto")
        self.assertIsNotNone(self.publisher.last("client/c1/ha/climate/homekit_ecobee_1/climate/config"))

    async def test_a_cleared_discovery_config_is_published_again(self):
        climate = "client/c1/ha/climate/homekit_ecobee_1/climate/config"
        self.assertIn(climate, self.publisher.watched)
        self.bridge.rediscovery_delay = 0
        # Zigbee2MQTT clears it when it starts; two clears give it back once.
        self.bridge.discovery_cleared(climate)
        self.bridge.discovery_cleared("client/c1/ha/sensor/homekit_ecobee_1/temperature/config")
        await self.bridge._rediscovery
        await self.bridge.flush()
        self.assertEqual(self.publisher.last(climate)["unique_id"], "homekit_ecobee_1_climate")
        self.assertEqual(self.publisher.topics().count(climate), 2)

    async def test_configs_not_published_are_not_given_back(self):
        self.bridge.rediscovery_delay = 0
        self.bridge.discovery_cleared("client/c1/ha/switch/0x0011223344556677/state/config")
        self.assertIsNone(self.bridge._rediscovery)

        # A device left out has its configs cleared by this service; they stay cleared.
        catalog = f"{BASE}/bridge/devices"
        self.bridge.taken.apply(catalog, json.dumps([{"friendly_name": "My ecobee", "ieee_address": "0x01"}]))
        with self.assertLogs("homekit_mqtt.bridge", "ERROR"):
            self.bridge.apply_names()
        await self.bridge.flush()
        self.bridge.discovery_cleared("client/c1/ha/climate/homekit_ecobee_1/climate/config")
        self.assertIsNone(self.bridge._rediscovery)


if __name__ == "__main__":
    unittest.main()
