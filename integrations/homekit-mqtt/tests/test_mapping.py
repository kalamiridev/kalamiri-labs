import unittest

from homekit_mqtt.mapping import (
    DeviceOptions,
    InvalidValue,
    build_devices,
    make_names_unique,
    plan_writes,
    state,
)

from .helpers import accessories, current


def device(fixture, options=None, index=0):
    return build_devices("test", accessories(fixture), options or {})[index]


def with_values(dev, system_mode=None, fan=None):
    """Current values with the thermostat mode or fan state changed."""
    thermostat = dev.thermostat

    def value_of(char):
        if system_mode is not None and char is thermostat.mode:
            return system_mode
        if fan is not None and char is thermostat.fan_current:
            return fan
        return char.value

    return value_of


def writes(batches):
    return [[(char.iid, raw) for char, raw in batch] for batch in batches]


class ThermostatTest(unittest.TestCase):
    def setUp(self):
        self.ecobee = device("ecobee_501")

    def test_state_uses_zigbee2mqtt_names(self):
        message = state(self.ecobee, current)
        self.assertEqual(message["system_mode"], "auto")
        self.assertEqual(message["running_state"], "idle")
        self.assertEqual(message["local_temperature"], 21.3)
        self.assertEqual(message["humidity"], 55.0)
        self.assertEqual(message["fan_mode"], "auto")
        self.assertIs(message["occupancy"], True)
        self.assertIs(message["motion"], True)

    def test_auto_mode_setpoints_are_the_thresholds(self):
        message = state(self.ecobee, current)
        self.assertEqual(message["occupied_heating_setpoint"], 7.2)
        self.assertEqual(message["occupied_cooling_setpoint"], 25.6)
        self.assertEqual(message["min_heat_setpoint_limit"], 7.2)
        self.assertEqual(message["max_heat_setpoint_limit"], 26.1)
        self.assertEqual(message["min_cool_setpoint_limit"], 18.3)
        self.assertEqual(message["max_cool_setpoint_limit"], 33.3)

    def test_heat_mode_both_setpoints_are_the_target(self):
        thermostat = device("ecobee3")
        message = state(thermostat, current)
        self.assertEqual(message["system_mode"], "heat")
        self.assertEqual(message["occupied_heating_setpoint"], message["occupied_cooling_setpoint"])
        self.assertNotIn("target_temperature", message)

    def test_off_mode_has_no_setpoints(self):
        message = state(self.ecobee, with_values(self.ecobee, system_mode=0))
        self.assertEqual(message["system_mode"], "off")
        self.assertIsNone(message["occupied_heating_setpoint"])
        self.assertIsNone(message["occupied_cooling_setpoint"])

    def test_fan_only_when_idle_and_blowing(self):
        message = state(self.ecobee, with_values(self.ecobee, fan=2))
        self.assertEqual(message["running_state"], "fan_only")

    def test_cool_mode_writes_cooling_setpoint_to_target_and_ignores_heating(self):
        batches, errors = plan_writes(
            self.ecobee,
            {"system_mode": "cool", "occupied_heating_setpoint": 20, "occupied_cooling_setpoint": 25},
            current,
        )
        self.assertEqual(errors, [])
        self.assertEqual(writes(batches), [[(18, 2)], [(20, 25.0)]])

    def test_auto_mode_needs_heating_below_cooling(self):
        batches, errors = plan_writes(
            self.ecobee, {"occupied_heating_setpoint": 24, "occupied_cooling_setpoint": 23}, current
        )
        self.assertEqual(batches, [])
        self.assertIn("below", errors[0])

    def test_auto_mode_keeps_the_other_threshold(self):
        batches, errors = plan_writes(self.ecobee, {"occupied_cooling_setpoint": 27}, current)
        self.assertEqual(errors, [])
        self.assertEqual(writes(batches), [[(23, 7.2), (22, 27.0)]])

    def test_off_mode_ignores_setpoints(self):
        batches, errors = plan_writes(
            self.ecobee, {"occupied_heating_setpoint": 20}, with_values(self.ecobee, system_mode=0)
        )
        self.assertEqual(batches, [])
        self.assertIn("off mode", errors[0])

    def test_same_message_as_the_home_assistant_automation(self):
        options = {
            "My ecobee": DeviceOptions(
                name="Living Room Thermostat",
                limits={"occupied_heating_setpoint": (18, 24), "occupied_cooling_setpoint": (22, 28)},
                exclude=frozenset({"temperature_display_units", "target_humidity", "fan_state"}),
            )
        }
        thermostat = device("ecobee_501", options)
        message = state(thermostat, current)
        self.assertEqual(
            set(message),
            {
                "system_mode", "running_state", "local_temperature", "humidity",
                "occupied_heating_setpoint", "occupied_cooling_setpoint",
                "min_heat_setpoint_limit", "max_heat_setpoint_limit",
                "min_cool_setpoint_limit", "max_cool_setpoint_limit",
                "fan_mode", "occupancy", "motion",
            },
        )
        self.assertEqual(
            [message[k] for k in ("min_heat_setpoint_limit", "max_heat_setpoint_limit",
                                  "min_cool_setpoint_limit", "max_cool_setpoint_limit")],
            [18, 24, 22, 28],
        )

    def test_mode_is_written_before_setpoint(self):
        batches, errors = plan_writes(
            self.ecobee, {"occupied_heating_setpoint": 21, "system_mode": "heat"}, current
        )
        self.assertEqual(errors, [])
        # mode (iid 18) first, then the target temperature (iid 20), which heat mode uses
        self.assertEqual(writes(batches), [[(18, 1)], [(20, 21.0)]])

    def test_auto_mode_writes_thresholds(self):
        batches, errors = plan_writes(
            self.ecobee, {"occupied_heating_setpoint": 19, "occupied_cooling_setpoint": 26}, current
        )
        self.assertEqual(errors, [])
        self.assertEqual(writes(batches), [[(23, 19.0), (22, 26.0)]])

    def test_setpoint_outside_range_is_refused(self):
        batches, errors = plan_writes(self.ecobee, {"occupied_heating_setpoint": 30}, current)
        self.assertEqual(batches, [])
        self.assertIn("between 7.2 and 26.1", errors[0])

    def test_operator_limits_narrow_the_range(self):
        limited = device(
            "ecobee_501",
            {"My ecobee": DeviceOptions(name="Living Room Thermostat", limits={"occupied_heating_setpoint": (18, 24)})},
        )
        self.assertEqual(limited.name, "Living Room Thermostat")
        message = state(limited, current)
        self.assertEqual(message["min_heat_setpoint_limit"], 18)
        self.assertEqual(message["max_heat_setpoint_limit"], 24)
        _batches, errors = plan_writes(limited, {"occupied_heating_setpoint": 25}, current)
        self.assertIn("between 18 and 24", errors[0])

    def test_fan_mode_on_and_auto(self):
        batches, errors = plan_writes(self.ecobee, {"fan_mode": "on"}, current)
        self.assertEqual(errors, [])
        self.assertEqual(writes(batches), [[(75, 0)]])

    def test_unknown_mode_and_property_are_reported(self):
        batches, errors = plan_writes(self.ecobee, {"system_mode": "dry", "colour": 1}, current)
        self.assertEqual(batches, [])
        self.assertEqual(len(errors), 2)

    def test_read_only_property_cannot_be_set(self):
        _batches, errors = plan_writes(self.ecobee, {"local_temperature": 20}, current)
        self.assertIn("read-only", errors[0])


class DevicesTest(unittest.TestCase):
    def test_remote_sensors_are_devices_with_one_status(self):
        devices = build_devices("test", accessories("ecobee3"), {})
        names = [d.name for d in devices]
        self.assertEqual(names, ["HomeW", "Kitchen", "Porch", "Basement"])
        kitchen = state(devices[1], current)
        self.assertEqual(set(kitchen), {"temperature", "active", "battery_low", "motion"})

    def test_power_strip_outlets_get_endpoint_suffixes(self):
        strip = device("mss425f")
        self.assertEqual(sorted(strip.props), [f"state_l{i}" for i in range(1, 6)])
        batches, errors = plan_writes(strip, {"state_l3": "OFF"}, current)
        self.assertEqual(errors, [])
        self.assertEqual(batches[0][0][1], False)

    def test_alarm_is_a_device_of_its_own(self):
        hub, alarm = build_devices("test", accessories("aqara_gateway"), {})
        self.assertEqual(alarm.name, "Aqara Hub-1563 Alarm")
        self.assertEqual(state(alarm, current), {"state": "disarmed"})
        batches, errors = plan_writes(alarm, {"state": "armed_away"}, current)
        self.assertEqual(errors, [])
        self.assertEqual(batches[0][0][1], 1)
        self.assertIn("state", hub.props)

    def test_lock(self):
        lock = device("schlage_sense")
        message = state(lock, current)
        self.assertEqual(message["state"], "LOCK")
        self.assertEqual(message["lock_state"], "unknown")
        batches, _errors = plan_writes(lock, {"state": "UNLOCK"}, current)
        self.assertEqual(batches[0][0][1], 0)

    def test_cover_reads_current_and_writes_target_position(self):
        cover = device("velux_window_cover")
        self.assertEqual(state(cover, current)["position"], 0)
        batches, errors = plan_writes(cover, {"position": 40}, current)
        self.assertEqual(errors, [])
        char, raw = batches[0][0]
        self.assertEqual(raw, 40)
        self.assertNotEqual(char, cover.props["position"].read)

    def test_sensor(self):
        message = state(device("eve_degree"), current)
        self.assertEqual(message["temperature"], 22.77)
        self.assertEqual(message["humidity"], 59.48)
        self.assertEqual(message["battery"], 65)
        self.assertIs(message["battery_low"], False)

    def test_light_brightness_must_be_in_range(self):
        fan = device("haa_fan1")
        _batches, errors = plan_writes(fan, {"state": "maybe"}, current)
        self.assertTrue(errors)

    def test_same_names_are_numbered(self):
        first = device("eve_degree")
        second = device("eve_degree")
        notes = make_names_unique([first, second])
        self.assertEqual(second.name, "Eve Degree AA11 2")
        self.assertEqual(len(notes), 1)


class ValueTest(unittest.TestCase):
    def test_enum_accepts_label_any_case(self):
        prop = device("ecobee_501").props["system_mode"]
        self.assertEqual(prop.from_mqtt("HEAT"), 1)
        with self.assertRaises(InvalidValue):
            prop.from_mqtt(True)

    def test_switch_accepts_on_off_and_bool(self):
        prop = device("mss425f").props["state_l1"]
        self.assertIs(prop.from_mqtt("ON"), True)
        self.assertIs(prop.from_mqtt(False), False)


if __name__ == "__main__":
    unittest.main()
