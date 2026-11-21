"""Map HomeKit accessories to MQTT devices.

A HomeKit accessory becomes one device. Its characteristics become properties of
one JSON state message. Common characteristics use the property names and
values of Zigbee2MQTT (``local_temperature``, ``occupancy``, ``state``), so a
consumer that understands Zigbee2MQTT understands these devices too. Every
other characteristic uses the snake_case name of its HomeKit type.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

from aiohomekit.model import Accessories, Accessory
from aiohomekit.model.characteristics import (
    Characteristic,
    CharacteristicFormats,
    CharacteristicPermissions,
    CharacteristicsTypes as C,
)
from aiohomekit.model.services import Service, ServicesTypes as S

APPLE_UUID_SUFFIX = "-0000-1000-8000-0026BB765291"

CHAR_NAMES = {
    value: key
    for key, value in vars(C).items()
    if key.isupper() and isinstance(value, str)
}

# Services that describe the accessory, not something it measures or controls.
SKIPPED_SERVICES = {
    S.ACCESSORY_INFORMATION,
    S.PROTOCOL_INFORMATION,
    S.SERVICE_LABEL,
    # Services for Apple's own use of the accessory: Siri and other voice assistants
    # built into it, audio and data streams to the Home hub, firmware updates,
    # Wi-Fi setup, access codes and diagnostics.
    S.SIRI,
    S.SIRI_ENDPOINT,
    S.ASSISTANT,
    S.AUDIO_STREAM_MANAGEMENT,
    S.DATA_STREAM_TRANSPORT_MANAGEMENT,
    S.ASSET_UPDATE,
    S.ACCESS_CONTROL,
    S.WI_FI_TRANSPORT,
    S.ACCESSORY_RUNTIME_INFORMATION,
    S.DIAGNOSTICS,
    S.ACCESSORY_METRICS,
}

# Characteristics that only name or identify a service.
SKIPPED_CHARACTERISTICS = {
    C.NAME,
    C.CONFIGURED_NAME,
    C.IDENTIFY,
    C.MANUFACTURER,
    C.MODEL,
    C.SERIAL_NUMBER,
    C.FIRMWARE_REVISION,
    C.HARDWARE_REVISION,
    C.IS_CONFIGURED,
}

# In a thermostat the heating and cooling setpoints follow the mode (see Thermostat).
THERMOSTAT_SETPOINT_TYPES = {
    C.TEMPERATURE_TARGET,
    C.TEMPERATURE_HEATING_THRESHOLD,
    C.TEMPERATURE_COOLING_THRESHOLD,
}

MODE_LABELS = {0: "off", 1: "heat", 2: "cool", 3: "auto"}
FAN_BLOWING = 2

# Status of the whole device, reported again by each of its sensor services.
DEVICE_STATUS = {
    C.STATUS_ACTIVE,
    C.STATUS_LO_BATT,
    C.STATUS_FAULT,
    C.STATUS_TAMPERED,
}

# Services that become a device of their own when the accessory has other services.
# An alarm keeps the plain property "state", which consumers read as the alarm state.
OWN_DEVICE_SERVICES = {S.SECURITY_SYSTEM}

HEATING_SETPOINT = "occupied_heating_setpoint"
COOLING_SETPOINT = "occupied_cooling_setpoint"


@dataclass(frozen=True)
class Spec:
    """How one characteristic type appears on MQTT."""

    name: str
    values: dict[int, Any] | None = None
    bool_like: bool = False
    inverted: bool = False


def _enum(name: str, values: dict[int, Any]) -> Spec:
    return Spec(name, values=values)


def _flag(name: str, inverted: bool = False) -> Spec:
    return Spec(name, bool_like=True, inverted=inverted)


ON_OFF = {0: "OFF", 1: "ON"}

# Characteristic type -> property, the same in every service.
SPECS: dict[str, Spec] = {
    C.TEMPERATURE_CURRENT: Spec("temperature"),
    C.RELATIVE_HUMIDITY_CURRENT: Spec("humidity"),
    C.RELATIVE_HUMIDITY_TARGET: Spec("target_humidity"),
    C.TEMPERATURE_TARGET: Spec("target_temperature"),
    C.TEMPERATURE_HEATING_THRESHOLD: Spec(HEATING_SETPOINT),
    C.TEMPERATURE_COOLING_THRESHOLD: Spec(COOLING_SETPOINT),
    C.HEATING_COOLING_CURRENT: _enum("running_state", {0: "idle", 1: "heat", 2: "cool"}),
    C.HEATING_COOLING_TARGET: _enum("system_mode", {0: "off", 1: "heat", 2: "cool", 3: "auto"}),
    C.CURRENT_HEATER_COOLER_STATE: _enum(
        "running_state", {0: "inactive", 1: "idle", 2: "heat", 3: "cool"}
    ),
    C.TARGET_HEATER_COOLER_STATE: _enum("system_mode", {0: "auto", 1: "heat", 2: "cool"}),
    C.TEMPERATURE_UNITS: _enum("temperature_display_units", {0: "celsius", 1: "fahrenheit"}),
    C.FAN_STATE_TARGET: _enum("fan_mode", {0: "manual", 1: "auto"}),
    C.FAN_STATE_CURRENT: _enum("fan_state", {0: "inactive", 1: "idle", 2: "blowing"}),
    C.ROTATION_SPEED: Spec("speed"),
    C.SWING_MODE: _enum("swing_mode", {0: "off", 1: "on"}),
    C.OCCUPANCY_DETECTED: _flag("occupancy"),
    C.MOTION_DETECTED: _flag("motion"),
    # HomeKit 0 means contact detected, which Zigbee2MQTT reports as contact: true (closed).
    C.CONTACT_STATE: _flag("contact", inverted=True),
    C.LEAK_DETECTED: _flag("water_leak"),
    C.SMOKE_DETECTED: _flag("smoke"),
    C.CARBON_MONOXIDE_DETECTED: _flag("carbon_monoxide"),
    C.CARBON_DIOXIDE_DETECTED: _flag("co2_detected"),
    C.CARBON_DIOXIDE_LEVEL: Spec("co2"),
    C.CARBON_MONOXIDE_LEVEL: Spec("co"),
    C.AIR_QUALITY: _enum(
        "air_quality",
        {0: "unknown", 1: "excellent", 2: "good", 3: "fair", 4: "inferior", 5: "poor"},
    ),
    C.DENSITY_PM25: Spec("pm25"),
    C.DENSITY_PM10: Spec("pm10"),
    C.DENSITY_VOC: Spec("voc"),
    C.LIGHT_LEVEL_CURRENT: Spec("illuminance"),
    C.BATTERY_LEVEL: Spec("battery"),
    C.STATUS_LO_BATT: _flag("battery_low"),
    C.STATUS_ACTIVE: _flag("active"),
    C.STATUS_FAULT: _flag("fault"),
    C.STATUS_TAMPERED: _flag("tamper"),
    C.ON: _enum("state", ON_OFF),
    C.ACTIVE: _enum("state", ON_OFF),
    C.IN_USE: _flag("in_use"),
    C.OUTLET_IN_USE: _flag("in_use"),
    C.BRIGHTNESS: Spec("brightness_percent"),
    C.COLOR_TEMPERATURE: Spec("color_temp"),
    C.HUE: Spec("hue"),
    C.SATURATION: Spec("saturation"),
    C.LOCK_MECHANISM_CURRENT_STATE: _enum(
        "lock_state", {0: "unlocked", 1: "locked", 2: "jammed", 3: "unknown"}
    ),
    C.LOCK_MECHANISM_TARGET_STATE: _enum("state", {0: "UNLOCK", 1: "LOCK"}),
    C.POSITION_CURRENT: Spec("position"),
    C.POSITION_STATE: _enum("moving", {0: "DOWN", 1: "UP", 2: "STOP"}),
    C.OBSTRUCTION_DETECTED: _flag("obstruction"),
    C.DOOR_STATE_CURRENT: _enum(
        "door_state", {0: "open", 1: "closed", 2: "opening", 3: "closing", 4: "stopped"}
    ),
    C.DOOR_STATE_TARGET: _enum("state", {0: "OPEN", 1: "CLOSE"}),
    C.SECURITY_SYSTEM_STATE_CURRENT: _enum(
        "state",
        {0: "armed_home", 1: "armed_away", 2: "armed_night", 3: "disarmed", 4: "triggered"},
    ),
    C.VOLUME: Spec("volume"),
    C.MUTE: _flag("mute"),
    C.ACTIVE_IDENTIFIER: Spec("input"),
}

# Read one characteristic, write another under the same property name.
WRITE_TARGETS: dict[str, tuple[str, dict[int, Any]]] = {
    C.POSITION_CURRENT: (C.POSITION_TARGET, {}),
    C.SECURITY_SYSTEM_STATE_CURRENT: (
        C.SECURITY_SYSTEM_STATE_TARGET,
        {0: "armed_home", 1: "armed_away", 2: "armed_night", 3: "disarmed"},
    ),
}
WRITE_ONLY_TARGETS = {target for target, _values in WRITE_TARGETS.values()}

# Inside a thermostat the fan modes are "on" and "auto", as in Zigbee2MQTT.
THERMOSTAT_SPEC_OVERRIDES: dict[str, Spec] = {
    C.TEMPERATURE_CURRENT: Spec("local_temperature"),
    C.FAN_STATE_TARGET: _enum("fan_mode", {0: "on", 1: "auto"}),
}


class InvalidValue(ValueError):
    """A value from MQTT that the characteristic does not accept."""


@dataclass
class Prop:
    """One MQTT property of a device."""

    name: str
    read: Characteristic | None
    write: Characteristic | None
    spec: Spec
    write_values: dict[int, Any] | None = None
    limits: tuple[float, float] | None = None

    @property
    def readable(self) -> bool:
        return self.read is not None

    @property
    def writable(self) -> bool:
        return self.write is not None

    def to_mqtt(self, raw: Any) -> Any:
        if raw is None:
            return None
        if self.spec.values is not None:
            return self.spec.values.get(raw, raw)
        if self.spec.bool_like:
            value = bool(raw)
            return not value if self.spec.inverted else value
        if isinstance(raw, float):
            return round(raw, 2) if math.isfinite(raw) else None
        return raw

    def from_mqtt(self, value: Any) -> Any:
        """Convert a value from an MQTT command to the raw HomeKit value."""
        char = self.write
        if char is None:
            raise InvalidValue(f"{self.name} is read-only")
        values = self.write_values if self.write_values is not None else self.spec.values
        if values:
            return _cast(char, _from_enum(self.name, value, values))
        if self.spec.bool_like:
            flag = _to_bool(self.name, value)
            raw = not flag if self.spec.inverted else flag
            return _cast(char, raw)
        return _check_number(self, char, value)

    def effective_range(self) -> tuple[float | None, float | None]:
        char = self.write or self.read
        low = char.minValue if char is not None else None
        high = char.maxValue if char is not None else None
        if self.limits is not None:
            low = self.limits[0] if low is None else max(low, self.limits[0])
            high = self.limits[1] if high is None else min(high, self.limits[1])
        return low, high


def _from_enum(name: str, value: Any, values: dict[int, Any]) -> int:
    if isinstance(value, str):
        wanted = value.strip().casefold()
        for raw, label in values.items():
            if isinstance(label, str) and label.casefold() == wanted:
                return raw
    if isinstance(value, bool):
        if values is ON_OFF:
            return int(value)
        raise InvalidValue(f"{name} does not accept {value!r}")
    if isinstance(value, int) and value in values:
        return value
    accepted = ", ".join(str(label) for label in values.values())
    raise InvalidValue(f"{name} must be one of: {accepted}")


def _to_bool(name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().upper() in ("ON", "TRUE"):
        return True
    if isinstance(value, str) and value.strip().upper() in ("OFF", "FALSE"):
        return False
    raise InvalidValue(f"{name} must be true or false")


def _cast(char: Characteristic, value: Any) -> Any:
    if char.format == CharacteristicFormats.bool:
        return bool(value)
    if char.format in INTEGER_FORMATS:
        return int(value)
    return value


INTEGER_FORMATS = {
    CharacteristicFormats.uint8,
    CharacteristicFormats.uint16,
    CharacteristicFormats.uint32,
    CharacteristicFormats.uint64,
    CharacteristicFormats.int,
}


def _check_number(prop: Prop, char: Characteristic, value: Any) -> Any:
    if char.format == CharacteristicFormats.string:
        if not isinstance(value, str):
            raise InvalidValue(f"{prop.name} must be text")
        return value
    if char.format == CharacteristicFormats.bool:
        return _to_bool(prop.name, value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidValue(f"{prop.name} must be a number")
    if not math.isfinite(value):
        raise InvalidValue(f"{prop.name} must be a finite number")
    low, high = prop.effective_range()
    if (low is not None and value < low) or (high is not None and value > high):
        raise InvalidValue(f"{prop.name} must be between {low} and {high}")
    if char.valid_values and int(value) not in char.valid_values:
        raise InvalidValue(f"{prop.name} must be one of {char.valid_values}")
    if char.format in INTEGER_FORMATS:
        if value != int(value):
            raise InvalidValue(f"{prop.name} must be a whole number")
        return int(value)
    step = char.minStep
    if step:
        value = round(round(value / step) * step, 4)
    return float(value)


@dataclass
class Thermostat:
    """Setpoints follow the mode, as Home Assistant shows a HomeKit thermostat.

    In heat or cool both setpoints are the target temperature. In auto they are
    the heating and cooling thresholds, when the thermostat has them. A
    thermostat with thresholds has no setpoint while it is off.
    """

    mode: Characteristic | None
    target: Characteristic | None
    heating: Characteristic | None
    cooling: Characteristic | None
    fan_current: Characteristic | None = None
    heating_limits: tuple[float, float] | None = None
    cooling_limits: tuple[float, float] | None = None
    step: float | None = None

    def characteristics(self) -> list[Characteristic]:
        chars = (self.mode, self.target, self.heating, self.cooling, self.fan_current)
        return [c for c in chars if c is not None]

    @property
    def has_thresholds(self) -> bool:
        return self.heating is not None and self.cooling is not None

    def setpoint_chars(self, mode_raw: Any) -> tuple[Characteristic | None, Characteristic | None]:
        """The characteristics behind the heating and cooling setpoints in a mode."""
        if mode_raw in (1, 2) or not self.has_thresholds:
            target = self.target or self.heating or self.cooling
            return target, target
        if mode_raw == 3:
            return self.heating, self.cooling
        return None, None

    def limits(self, name: str) -> tuple[float, float] | None:
        return self.heating_limits if name == HEATING_SETPOINT else self.cooling_limits

    def range_for(self, name: str) -> tuple[float | None, float | None]:
        source = self.heating if name == HEATING_SETPOINT else self.cooling
        source = source or self.target
        low = source.minValue if source is not None else None
        high = source.maxValue if source is not None else None
        limits = self.limits(name)
        if limits is not None:
            low = limits[0] if low is None else max(low, limits[0])
            high = limits[1] if high is None else min(high, limits[1])
        return low, high


@dataclass
class ServicePart:
    """A service of the device and the names of its properties."""

    service: Service
    suffix: str
    names: list[str]


@dataclass
class Device:
    """One HomeKit accessory as an MQTT device."""

    alias: str
    aid: int
    name: str
    accessory_name: str
    manufacturer: str
    model: str
    serial: str
    firmware: str
    props: dict[str, Prop] = field(default_factory=dict)
    thermostat: Thermostat | None = None
    services: list[ServicePart] = field(default_factory=list)

    part: str = ""

    @property
    def key(self) -> str:
        return f"{self.alias}:{self.aid}{self.part}"

    def readable_chars(self) -> list[Characteristic]:
        chars = {(c.service.accessory.aid, c.iid): c for c in self._all_read_chars()}
        return list(chars.values())

    def _all_read_chars(self):
        for prop in self.props.values():
            if prop.read is not None:
                yield prop.read
        if self.thermostat is not None:
            for char in self.thermostat.characteristics():
                if CharacteristicPermissions.paired_read in char.perms:
                    yield char

    def event_chars(self) -> list[Characteristic]:
        return [
            c for c in self.readable_chars() if CharacteristicPermissions.events in c.perms
        ]


@dataclass(frozen=True)
class DeviceOptions:
    """What the operator set for one accessory in the devices file."""

    name: str | None = None
    limits: dict[str, tuple[float, float]] = field(default_factory=dict)
    exclude: frozenset[str] = frozenset()
    # Setpoint step of a thermostat in Home Assistant; None keeps the step of the accessory.
    step: float | None = None


def _apple(char_type: str) -> bool:
    return char_type.upper().endswith(APPLE_UUID_SUFFIX)


def _include(char: Characteristic, include_vendor: bool) -> bool:
    if char.type in SKIPPED_CHARACTERISTICS:
        return False
    if CharacteristicPermissions.hidden in char.perms:
        return False
    if char.format in (CharacteristicFormats.tlv8, CharacteristicFormats.data):
        return False
    if char.type not in CHAR_NAMES:
        return False
    if not _apple(char.type) and not include_vendor:
        return False
    readable = CharacteristicPermissions.paired_read in char.perms
    writable = CharacteristicPermissions.paired_write in char.perms
    return readable or writable


def _spec(service: Service, char: Characteristic) -> Spec:
    if service.type == S.THERMOSTAT and char.type in THERMOSTAT_SPEC_OVERRIDES:
        return THERMOSTAT_SPEC_OVERRIDES[char.type]
    if char.type in SPECS:
        return SPECS[char.type]
    return Spec(CHAR_NAMES[char.type].lower())


def _info(accessory: Accessory, char_type: str) -> str:
    service = accessory.services.first(service_type=S.ACCESSORY_INFORMATION)
    if service is None:
        return ""
    value = service.value(char_type, "")
    return value.strip() if isinstance(value, str) else ""


def _service_props(
    service: Service, include_vendor: bool, limits: dict[str, tuple[float, float]]
) -> tuple[list[Prop], Thermostat | None]:
    props: list[Prop] = []
    thermostat = None
    chars = list(service.characteristics)

    if service.type == S.THERMOSTAT:
        by_type = {c.type: c for c in chars}
        thermostat = Thermostat(
            mode=by_type.get(C.HEATING_COOLING_TARGET),
            target=by_type.get(C.TEMPERATURE_TARGET),
            heating=by_type.get(C.TEMPERATURE_HEATING_THRESHOLD),
            cooling=by_type.get(C.TEMPERATURE_COOLING_THRESHOLD),
            fan_current=by_type.get(C.FAN_STATE_CURRENT),
            heating_limits=limits.get(HEATING_SETPOINT),
            cooling_limits=limits.get(COOLING_SETPOINT),
        )
        chars = [c for c in chars if c.type not in THERMOSTAT_SETPOINT_TYPES]

    for char in chars:
        if char.type in WRITE_ONLY_TARGETS or not _include(char, include_vendor):
            continue
        spec = _spec(service, char)
        readable = CharacteristicPermissions.paired_read in char.perms
        writable = CharacteristicPermissions.paired_write in char.perms
        write = char if writable else None
        write_values = None
        if char.type in WRITE_TARGETS:
            target_type, target_values = WRITE_TARGETS[char.type]
            target = next((c for c in service.characteristics if c.type == target_type), None)
            if target is not None and CharacteristicPermissions.paired_write in target.perms:
                write = target
            write_values = target_values or None
        props.append(
            Prop(
                name=spec.name,
                read=char if readable else None,
                write=write,
                spec=spec,
                write_values=write_values,
                limits=limits.get(spec.name),
            )
        )
    return props, thermostat


def build_device(
    alias: str,
    accessory: Accessory,
    options: DeviceOptions | None = None,
    include_vendor: bool = False,
    services: list[Service] | None = None,
    part: str = "",
    default_name: str | None = None,
) -> Device:
    """Describe one accessory, or some of its services, as an MQTT device."""
    options = options or DeviceOptions()
    accessory_name = _info(accessory, C.NAME) or f"{alias} {accessory.aid}"
    device = Device(
        alias=alias,
        aid=accessory.aid,
        name=options.name or default_name or accessory_name,
        accessory_name=accessory_name,
        manufacturer=_info(accessory, C.MANUFACTURER),
        model=_info(accessory, C.MODEL),
        serial=_info(accessory, C.SERIAL_NUMBER),
        firmware=_info(accessory, C.FIRMWARE_REVISION),
        part=part,
    )

    per_service: list[tuple[Service, list[Prop]]] = []
    status_seen: set[str] = set()
    for service in services if services is not None else accessory.services:
        if service.type in SKIPPED_SERVICES:
            continue
        props, thermostat = _service_props(service, include_vendor, options.limits)
        kept = []
        for prop in props:
            char = prop.read or prop.write
            if char is not None and char.type in DEVICE_STATUS:
                if char.type in status_seen:
                    continue
                status_seen.add(char.type)
            kept.append(prop)
        props = kept
        if thermostat is not None and device.thermostat is None:
            thermostat.step = options.step
            device.thermostat = thermostat
        if props or thermostat is not None:
            per_service.append((service, props))

    # A name used by more than one service gets an endpoint suffix, as in Zigbee2MQTT.
    counts: dict[str, int] = {}
    for _service, props in per_service:
        for name in {p.name for p in props}:
            counts[name] = counts.get(name, 0) + 1
    if device.thermostat is not None:
        for name in (HEATING_SETPOINT, COOLING_SETPOINT):
            counts[name] = counts.get(name, 0) + 1

    seen: dict[str, int] = {}
    for service, props in per_service:
        suffix = ""
        shared = [p.name for p in props if counts[p.name] > 1]
        if shared:
            index = seen.get(shared[0], 0) + 1
            for name in shared:
                seen[name] = index
            suffix = f"_l{index}"
        names = []
        for prop in props:
            if counts[prop.name] > 1:
                prop.name = f"{prop.name}_l{seen[prop.name]}"
            device.props[prop.name] = prop
            names.append(prop.name)
        device.services.append(ServicePart(service, suffix, names))

    for name in options.exclude:
        device.props.pop(name, None)
    for part in device.services:
        part.names = [n for n in part.names if n not in options.exclude]
    return device


def build_devices(
    alias: str,
    accessories: Accessories,
    options: dict[str, DeviceOptions],
    include_vendor: bool = False,
) -> list[Device]:
    """All accessories of one pairing. Options are matched by accessory name or alias:aid."""
    devices = []
    for accessory in accessories:
        name = _info(accessory, C.NAME) or f"{alias} {accessory.aid}"
        relevant = [s for s in accessory.services if s.type not in SKIPPED_SERVICES]
        own = [s for s in relevant if s.type in OWN_DEVICE_SERVICES]
        parts: list[tuple[list[Service], str, str | None]] = []
        if own and len(own) < len(relevant):
            parts.append(([s for s in relevant if s not in own], "", None))
            for index, service in enumerate(own, start=1):
                label = "Alarm" if len(own) == 1 else f"Alarm {index}"
                parts.append(([service], f":alarm{index}", f"{name} {label}"))
        else:
            parts.append((relevant, "", None))
        for services, part, default_name in parts:
            chosen = options.get(f"{alias}:{accessory.aid}{part}")
            if chosen is None and not part:
                chosen = options.get(name)
            if chosen is None and default_name:
                chosen = options.get(default_name)
            device = build_device(
                alias, accessory, chosen, include_vendor, services, part, default_name
            )
            if device.props or device.thermostat is not None:
                devices.append(device)
    return devices


def make_names_unique(devices: list[Device]) -> list[str]:
    """Give devices with the same name a number; return a note for each rename."""
    notes = []
    used: set[str] = set()
    for device in devices:
        base = device.name
        name = base
        number = 2
        while name.casefold() in used:
            name = f"{base} {number}"
            number += 1
        if name != base:
            notes.append(f"{device.key} {base!r} renamed to {name!r}")
            device.name = name
        used.add(name.casefold())
    return notes


ValueLookup = Callable[[Characteristic], Any]


def _setpoint(thermostat: Thermostat, name: str, value: Any, errors: list[str]) -> float | None:
    low, high = thermostat.range_for(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        errors.append(f"{name} must be a number")
        return None
    if (low is not None and value < low) or (high is not None and value > high):
        errors.append(f"{name} must be between {low} and {high}")
        return None
    return float(value)


def _stepped(char: Characteristic, value: float) -> float:
    step = char.minStep or 0
    return round(round(value / step) * step, 4) if step else value


def _writable(char: Characteristic | None) -> bool:
    return char is not None and CharacteristicPermissions.paired_write in char.perms


def _setpoint_writes(
    thermostat: Thermostat,
    command: dict[str, Any],
    mode_raw: Any,
    value_of: ValueLookup,
    errors: list[str],
) -> list[tuple[Characteristic, Any]]:
    """Setpoint writes for the mode the thermostat is in after the command."""
    given = [n for n in (HEATING_SETPOINT, COOLING_SETPOINT) if n in command]
    if not given:
        return []
    mode = MODE_LABELS.get(mode_raw, "unknown")

    if mode_raw in (1, 2) or not thermostat.has_thresholds:
        # One target temperature: the setpoint of the mode counts, the other is ignored.
        target, _ = thermostat.setpoint_chars(mode_raw)
        wanted = COOLING_SETPOINT if mode_raw == 2 else HEATING_SETPOINT
        if mode_raw not in (1, 2) and wanted not in given:
            wanted = given[0]
        if wanted not in given:
            return []
        value = _setpoint(thermostat, wanted, command[wanted], errors)
        if value is None:
            return []
        if not _writable(target):
            errors.append(f"{wanted} cannot be set")
            return []
        return [(target, _stepped(target, value))]

    if mode_raw == 3:
        numbers = {n: _setpoint(thermostat, n, command[n], errors) for n in given}
        if any(numbers[n] is None for n in given):
            return []
        low = numbers.get(HEATING_SETPOINT, value_of(thermostat.heating))
        high = numbers.get(COOLING_SETPOINT, value_of(thermostat.cooling))
        if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
            errors.append("the current setpoints are not known yet")
            return []
        if low >= high:
            errors.append(f"{HEATING_SETPOINT} must be below {COOLING_SETPOINT}")
            return []
        if not (_writable(thermostat.heating) and _writable(thermostat.cooling)):
            errors.append("the setpoints cannot be set")
            return []
        return [
            (thermostat.heating, _stepped(thermostat.heating, float(low))),
            (thermostat.cooling, _stepped(thermostat.cooling, float(high))),
        ]

    for name in given:
        errors.append(f"{name} is not used in {mode} mode")
    return []


def state(device: Device, value_of: ValueLookup) -> dict[str, Any]:
    """The state message of a device, from current characteristic values."""
    result: dict[str, Any] = {}
    for prop in device.props.values():
        if prop.read is None:
            continue
        value = prop.to_mqtt(value_of(prop.read))
        if value is not None:
            result[prop.name] = value

    thermostat = device.thermostat
    if thermostat is not None:
        mode_raw = value_of(thermostat.mode) if thermostat.mode is not None else None
        if (
            result.get("running_state") == "idle"
            and thermostat.fan_current is not None
            and value_of(thermostat.fan_current) == FAN_BLOWING
        ):
            # Only the fan runs, as Home Assistant reports it.
            result["running_state"] = "fan_only"
        heating, cooling = thermostat.setpoint_chars(mode_raw)
        for name, char in ((HEATING_SETPOINT, heating), (COOLING_SETPOINT, cooling)):
            value = value_of(char) if char is not None else None
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                result[name] = round(float(value), 2)
            else:
                result[name] = None
        for name, prefix in ((HEATING_SETPOINT, "heat"), (COOLING_SETPOINT, "cool")):
            low, high = thermostat.range_for(name)
            if low is not None:
                result[f"min_{prefix}_setpoint_limit"] = low
            if high is not None:
                result[f"max_{prefix}_setpoint_limit"] = high
    return result


def plan_writes(
    device: Device, command: dict[str, Any], value_of: ValueLookup
) -> tuple[list[list[tuple[Characteristic, Any]]], list[str]]:
    """Turn an MQTT command into batches of characteristic writes.

    A thermostat mode is written in its own first batch, because which
    characteristic holds a setpoint depends on the mode. Returns the batches
    and an error for each value that was refused.
    """
    errors: list[str] = []
    first: list[tuple[Characteristic, Any]] = []
    rest: list[tuple[Characteristic, Any]] = []
    thermostat = device.thermostat
    mode_raw = value_of(thermostat.mode) if thermostat and thermostat.mode else None

    for name, value in command.items():
        if name in (HEATING_SETPOINT, COOLING_SETPOINT) and thermostat is not None:
            continue
        prop = device.props.get(name)
        if prop is None:
            errors.append(f"{name} is not a property of {device.name}")
            continue
        try:
            raw = prop.from_mqtt(value)
        except InvalidValue as exc:
            errors.append(str(exc))
            continue
        if thermostat is not None and prop.write is thermostat.mode:
            first.append((prop.write, raw))
            mode_raw = raw
        else:
            rest.append((prop.write, raw))

    if thermostat is not None:
        rest.extend(_setpoint_writes(thermostat, command, mode_raw, value_of, errors))

    batches = [batch for batch in (first, rest) if batch]
    return batches, errors
