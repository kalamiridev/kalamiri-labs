import json
import unittest

from homekit_mqtt.names import TakenNames

BASE = "client/c1/sl-gw-1"


def catalog(*names):
    return json.dumps([{"friendly_name": name, "ieee_address": f"0x{i}"} for i, name in enumerate(names)])


class TakenNamesTest(unittest.TestCase):
    def setUp(self):
        self.taken = TakenNames(BASE, "homekit-mqtt")

    def test_the_gateways_catalog_keeps_its_names(self):
        self.assertTrue(self.taken.apply(f"{BASE}/bridge/devices", catalog("Coordinator", "Living Room TV")))
        self.assertEqual(self.taken.owner("Living Room TV"), f"{BASE}/bridge/devices")
        self.assertIsNone(self.taken.owner("Bedroom TV"))

    def test_only_services_named_before_this_one_keep_their_names(self):
        self.assertTrue(self.taken.apply(f"{BASE}/fusionsolar-mqtt/bridge/devices", catalog("Hall TV")))
        self.assertFalse(self.taken.apply(f"{BASE}/tv-mqtt/bridge/devices", catalog("Living Room TV")))
        self.assertFalse(self.taken.apply(f"{BASE}/zz-mqtt/bridge/devices", catalog("Bedroom TV")))
        self.assertEqual(self.taken.owner("Hall TV"), f"{BASE}/fusionsolar-mqtt/bridge/devices")
        self.assertIsNone(self.taken.owner("Living Room TV"))
        self.assertIsNone(self.taken.owner("Bedroom TV"))

    def test_a_rename_frees_the_name(self):
        self.taken.apply(f"{BASE}/bridge/devices", catalog("Living Room TV"))
        self.assertFalse(self.taken.apply(f"{BASE}/bridge/devices", catalog("Living Room TV")))
        self.assertTrue(self.taken.apply(f"{BASE}/bridge/devices", catalog("Living Room TV Plug")))
        self.assertIsNone(self.taken.owner("Living Room TV"))

    def test_an_empty_message_removes_the_catalog(self):
        self.taken.apply(f"{BASE}/fusionsolar-mqtt/bridge/devices", catalog("Hall TV"))
        self.assertTrue(self.taken.apply(f"{BASE}/fusionsolar-mqtt/bridge/devices", b""))
        self.assertIsNone(self.taken.owner("Hall TV"))

    def test_an_unreadable_catalog_keeps_the_names(self):
        self.taken.apply(f"{BASE}/bridge/devices", catalog("Living Room TV"))
        with self.assertLogs("homekit_mqtt.names", "WARNING"):
            self.assertFalse(self.taken.apply(f"{BASE}/bridge/devices", b"{"))
        self.assertIsNotNone(self.taken.owner("Living Room TV"))

    def test_other_topics_are_not_catalogs(self):
        self.assertFalse(self.taken.apply(f"{BASE}/Living Room TV", json.dumps({"state": "ON"})))
        self.assertFalse(self.taken.apply("client/c1/sl-gw-2/bridge/devices", catalog("Living Room TV")))
        self.assertIsNone(self.taken.owner("Living Room TV"))


if __name__ == "__main__":
    unittest.main()
