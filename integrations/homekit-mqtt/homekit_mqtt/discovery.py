"""Home Assistant MQTT discovery for HomeKit devices.

Common HomeKit services get a matching Home Assistant entity: thermostat,
light, switch and outlet, fan, lock, window covering, garage door, security
system, and sensors. Every property is on MQTT either way; discovery only adds
entities for the services listed here.
"""

from __future__ import annotations

import json
import re
from typing import Any

from aiohomekit.model.services import ServicesTypes as S

from .mapping import COOLING_SETPOINT, HEATING_SETPOINT, Device

SUFFIX = re.compile(r"_l\d+$")

# Marks a key of the shared config that an entity must not have.
DROP = object()

# Base property name -> (device_class, unit, state_class)
SENSORS: dict[str, tuple[str | None, str | None]] = {
    "temperature": ("temperature", "°C"),
    "humidity": ("humidity", "%"),
    "illuminance": ("illuminance", "lx"),
    "co2": ("carbon_dioxide", "ppm"),
    "co": ("carbon_monoxide", "ppm"),
    "pm25": ("pm25", "µg/m³"),
    "pm10": ("pm10", "µg/m³"),
    "voc": ("volatile_organic_compounds", "µg/m³"),
    "battery": ("battery", "%"),
}

# Base property name -> (device_class, inverted)
BINARY_SENSORS: dict[str, tuple[str, bool]] = {
    "occupancy": ("occupancy", False),
    "motion": ("motion", False),
    "contact": ("door", True),
    "water_leak": ("moisture", False),
    "smoke": ("smoke", False),
    "carbon_monoxide": ("carbon_monoxide", False),
    "battery_low": ("battery", False),
    "tamper": ("tamper", False),
    "obstruction": ("problem", False),
    "fault": ("problem", False),
}

LIGHTS = {S.LIGHTBULB}
SWITCHES = {S.SWITCH, S.OUTLET}
FANS = {S.FAN, S.FAN_V2}


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", text).strip("_").lower()
    return slug or "device"


def _base(name: str) -> str:
    return SUFFIX.sub("", name)


def _label(name: str) -> str:
    base = _base(name).replace("_", " ").capitalize()
    match = SUFFIX.search(name)
    return f"{base} {match.group(0)[2:]}" if match else base


def discovery_messages(
    device: Device, base_topic: str, prefix: str, bridge_availability: str
) -> list[tuple[str, dict[str, Any]]]:
    """Discovery topics and configs for one device."""
    state_topic = f"{base_topic}/{device.name}"
    command_topic = f"{state_topic}/set"
    node = _slug(f"homekit_{device.alias}_{device.aid}{device.part}")
    device_info = {
        "identifiers": [node],
        "name": device.name,
        "manufacturer": device.manufacturer or None,
        "model": device.model or None,
        "serial_number": device.serial or None,
        "sw_version": device.firmware or None,
    }
    device_info = {k: v for k, v in device_info.items() if v is not None}
    common = {
        "device": device_info,
        "availability": [
            {"topic": f"{state_topic}/availability", "value_template": "{{ value_json.state }}"},
            {"topic": bridge_availability, "value_template": "{{ value_json.state }}"},
        ],
        "availability_mode": "all",
        "state_topic": state_topic,
    }

    messages: list[tuple[str, dict[str, Any]]] = []
    used: set[str] = set()

    def add(component: str, object_id: str, config: dict[str, Any]) -> None:
        merged = {**common, "unique_id": f"{node}_{object_id}", **config}
        merged = {k: v for k, v in merged.items() if v is not DROP}
        messages.append((f"{prefix}/{component}/{node}/{object_id}/config", merged))

    props = device.props

    if device.thermostat is not None:
        add("climate", "climate", _climate(device, state_topic, command_topic))
        for part in device.services:
            if part.service.type == S.THERMOSTAT:
                used.update(part.names)
        used.update({HEATING_SETPOINT, COOLING_SETPOINT})

    for part in device.services:
        names = part.names
        kind = part.service.type
        key = lambda base: next((n for n in names if _base(n) == base), None)  # noqa: E731
        state = key("state")

        if kind in LIGHTS and state:
            brightness = key("brightness_percent")
            color_temp = key("color_temp")
            on = '"' + state + '": "ON"'
            if brightness:
                on += '{% if brightness is defined %}, "' + brightness + '": {{ (brightness / 2.55) | round(0) | int }}{% endif %}'
            if color_temp:
                on += '{% if color_temp is defined %}, "' + color_temp + '": {{ color_temp }}{% endif %}'
            config = {
                "name": None if not part.suffix else _label(state).replace("State", "Light"),
                "schema": "template",
                "command_topic": command_topic,
                "command_on_template": "{" + on + "}",
                "command_off_template": json.dumps({state: "OFF"}),
                "state_template": "{{ value_json['" + state + "'] | lower }}",
            }
            if brightness:
                config["brightness_template"] = (
                    "{{ (value_json['" + brightness + "'] * 2.55) | round(0) | int }}"
                )
            if color_temp:
                config["color_temp_template"] = "{{ value_json['" + color_temp + "'] }}"
            add("light", f"light{part.suffix}", config)
            used.update(n for n in (state, brightness, color_temp) if n)

        elif kind in SWITCHES and state:
            add(
                "switch",
                f"switch{part.suffix}",
                {
                    "name": None if not part.suffix else _label(state).replace("State", "Switch"),
                    "command_topic": command_topic,
                    "value_template": "{{ value_json['" + state + "'] }}",
                    "state_on": "ON",
                    "state_off": "OFF",
                    "payload_on": json.dumps({state: "ON"}),
                    "payload_off": json.dumps({state: "OFF"}),
                },
            )
            used.add(state)

        elif kind in FANS and state:
            config = {
                "name": None if not part.suffix else _label(state).replace("State", "Fan"),
                "command_topic": command_topic,
                "state_value_template": "{{ value_json['" + state + "'] }}",
                "payload_on": json.dumps({state: "ON"}),
                "payload_off": json.dumps({state: "OFF"}),
            }
            speed = key("speed")
            if speed:
                config.update(
                    {
                        "percentage_state_topic": f"{base_topic}/{device.name}",
                        "percentage_value_template": "{{ value_json['" + speed + "'] }}",
                        "percentage_command_topic": command_topic,
                        "percentage_command_template": '{"' + speed + '": {{ value }}}',
                    }
                )
            add("fan", f"fan{part.suffix}", config)
            used.update(n for n in (state, speed) if n)

        elif kind == S.LOCK_MECHANISM and state:
            lock_state = key("lock_state")
            add(
                "lock",
                f"lock{part.suffix}",
                {
                    "name": None,
                    "command_topic": command_topic,
                    "value_template": "{{ value_json['" + (lock_state or state) + "'] }}",
                    "state_locked": "locked" if lock_state else "LOCK",
                    "state_unlocked": "unlocked" if lock_state else "UNLOCK",
                    "state_jammed": "jammed",
                    "payload_lock": json.dumps({state: "LOCK"}),
                    "payload_unlock": json.dumps({state: "UNLOCK"}),
                },
            )
            used.update(n for n in (state, lock_state) if n)

        elif kind == S.WINDOW_COVERING and key("position"):
            position = key("position")
            config = {
                "name": None,
                "position_topic": state_topic,
                "position_template": "{{ value_json['" + position + "'] }}",
                "state_topic": DROP,
            }
            if props[position].writable:
                config.update(
                    {
                        "command_topic": command_topic,
                        "payload_open": json.dumps({position: 100}),
                        "payload_close": json.dumps({position: 0}),
                        "payload_stop": None,
                        "set_position_topic": command_topic,
                        "set_position_template": '{"' + position + '": {{ position }}}',
                    }
                )
            add("cover", f"cover{part.suffix}", config)
            used.update(n for n in (position, key("moving")) if n)

        elif kind == S.GARAGE_DOOR_OPENER and key("door_state"):
            door = key("door_state")
            config = {
                "name": None,
                "device_class": "garage",
                "value_template": "{{ value_json['" + door + "'] }}",
                "state_open": "open",
                "state_closed": "closed",
                "state_opening": "opening",
                "state_closing": "closing",
                "state_stopped": "stopped",
                "payload_stop": None,
            }
            if state:
                config.update(
                    {
                        "command_topic": command_topic,
                        "payload_open": json.dumps({state: "OPEN"}),
                        "payload_close": json.dumps({state: "CLOSE"}),
                    }
                )
            add("cover", f"garage{part.suffix}", config)
            used.update(n for n in (door, state) if n)

        elif kind == S.SECURITY_SYSTEM and state:
            config = {
                "name": None,
                "value_template": "{{ value_json['" + state + "'] }}",
                "code_arm_required": False,
                "code_disarm_required": False,
                "supported_features": ["arm_home", "arm_away", "arm_night"],
            }
            if props[state].writable:
                config.update(
                    {
                        "command_topic": command_topic,
                        "command_template": (
                            '{"' + state + '": "{{ {"ARM_HOME": "armed_home", '
                            '"ARM_AWAY": "armed_away", "ARM_NIGHT": "armed_night", '
                            '"DISARM": "disarmed"}[action] }}"}'
                        ),
                    }
                )
            add("alarm_control_panel", f"alarm{part.suffix}", config)
            used.add(state)

    for name, prop in props.items():
        if name in used or prop.read is None:
            continue
        base = _base(name)
        if base in SENSORS:
            device_class, unit = SENSORS[base]
            add(
                "sensor",
                name,
                {
                    "name": _label(name),
                    "device_class": device_class,
                    "unit_of_measurement": unit,
                    "state_class": "measurement",
                    "value_template": "{{ value_json['" + name + "'] }}",
                },
            )
        elif base in BINARY_SENSORS:
            device_class, inverted = BINARY_SENSORS[base]
            on = "false" if inverted else "true"
            add(
                "binary_sensor",
                name,
                {
                    "name": _label(name),
                    "device_class": device_class,
                    "value_template": (
                        "{{ 'ON' if (value_json['" + name + "'] | string | lower) == '" + on + "' else 'OFF' }}"
                    ),
                },
            )

    return messages


def _climate(device: Device, state_topic: str, command_topic: str) -> dict[str, Any]:
    props = device.props
    thermostat = device.thermostat
    assert thermostat is not None
    modes = ["off", "heat", "cool", "heat_cool"]
    if thermostat.mode is not None and thermostat.mode.valid_values:
        labels = {0: "off", 1: "heat", 2: "cool", 3: "heat_cool"}
        modes = [labels[v] for v in thermostat.mode.valid_values if v in labels]
    low, _ = thermostat.range_for(HEATING_SETPOINT)
    _, high = thermostat.range_for(COOLING_SETPOINT)
    config: dict[str, Any] = {
        "name": None,
        "state_topic": DROP,
        "temperature_unit": "C",
        "precision": 0.1,
        "modes": modes,
        "mode_state_topic": state_topic,
        "mode_state_template": (
            "{{ {'auto': 'heat_cool'}.get(value_json.system_mode, value_json.system_mode) }}"
        ),
        "mode_command_topic": command_topic,
        "mode_command_template": '{"system_mode": "{{ {"heat_cool": "auto"}.get(value, value) }}"}',
        "current_temperature_topic": state_topic,
        "current_temperature_template": "{{ value_json.local_temperature }}",
        "temperature_low_state_topic": state_topic,
        "temperature_low_state_template": "{{ value_json.occupied_heating_setpoint }}",
        "temperature_low_command_topic": command_topic,
        "temperature_low_command_template": '{"occupied_heating_setpoint": {{ value }}}',
        "temperature_high_state_topic": state_topic,
        "temperature_high_state_template": "{{ value_json.occupied_cooling_setpoint }}",
        "temperature_high_command_topic": command_topic,
        "temperature_high_command_template": '{"occupied_cooling_setpoint": {{ value }}}',
    }
    # In heat or cool both setpoints are the target temperature; the service uses the one of the mode.
    config.update(
        {
            "temperature_state_topic": state_topic,
            "temperature_state_template": (
                "{{ value_json.occupied_cooling_setpoint if value_json.system_mode == 'cool' "
                "else value_json.occupied_heating_setpoint }}"
            ),
            "temperature_command_topic": command_topic,
            "temperature_command_template": (
                '{"occupied_heating_setpoint": {{ value }}, "occupied_cooling_setpoint": {{ value }}}'
            ),
        }
    )
    if low is not None:
        config["min_temp"] = low
    if high is not None:
        config["max_temp"] = high
    if "humidity" in props:
        config["current_humidity_topic"] = state_topic
        config["current_humidity_template"] = "{{ value_json.humidity }}"
    if "running_state" in props:
        config["action_topic"] = state_topic
        config["action_template"] = (
            "{{ {'heat': 'heating', 'cool': 'cooling', 'idle': 'idle'}"
            ".get(value_json.running_state, 'idle') }}"
        )
    if "fan_mode" in props and props["fan_mode"].writable:
        config.update(
            {
                "fan_modes": ["on", "auto"],
                "fan_mode_state_topic": state_topic,
                "fan_mode_state_template": "{{ value_json.fan_mode }}",
                "fan_mode_command_topic": command_topic,
                "fan_mode_command_template": '{"fan_mode": "{{ value }}"}',
            }
        )
    return config
