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

    async def publish(self, topic, payload, retain=True):
        self.messages.append((topic, json.loads(payload), retain))

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


if __name__ == "__main__":
    unittest.main()
