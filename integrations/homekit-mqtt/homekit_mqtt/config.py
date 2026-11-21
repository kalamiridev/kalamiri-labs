"""Settings from the environment and the optional devices file."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .mapping import DeviceOptions

FORBIDDEN_TOPIC_CHARACTERS = ("+", "#", "\x00")


class ConfigError(RuntimeError):
    """A setting is missing or wrong."""


@dataclass(frozen=True)
class Config:
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str
    mqtt_tls: bool
    mqtt_client_id: str
    base_topic: str
    bridge_name: str
    discovery_enabled: bool
    discovery_prefix: str
    data_dir: Path
    poll_interval: int
    include_vendor: bool
    devices: dict[str, DeviceOptions]

    @property
    def pairing_file(self) -> Path:
        return self.data_dir / "pairing.json"

    @property
    def charmap_file(self) -> Path:
        return self.data_dir / "charmap.json"

    @property
    def bridge_availability_topic(self) -> str:
        return f"{self.base_topic}/{self.bridge_name}/availability"


def _text(env: Mapping[str, str], name: str, default: str = "") -> str:
    return env.get(name, default).strip()


def _required(env: Mapping[str, str], name: str) -> str:
    value = _text(env, name)
    if not value:
        raise ConfigError(f"{name} is required")
    return value


def _bool(env: Mapping[str, str], name: str, default: str) -> bool:
    value = _text(env, name, default).lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be true or false")


def _int(env: Mapping[str, str], name: str, default: str, low: int, high: int) -> int:
    try:
        value = int(_text(env, name, default))
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number") from exc
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low} and {high}")
    return value


def _topic(name: str, value: str) -> str:
    value = value.strip("/")
    if not value or any(c in value for c in FORBIDDEN_TOPIC_CHARACTERS):
        raise ConfigError(f"{name} must be an MQTT topic without + or #")
    return value


def load_devices(path: Path) -> dict[str, DeviceOptions]:
    """Read the optional devices file: names, setpoint limits and step, and left-out properties per accessory."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain an object of accessories")

    devices: dict[str, DeviceOptions] = {}
    for key, entry in data.items():
        if not isinstance(entry, dict):
            raise ConfigError(f"{path}: {key!r} must be an object")
        name = entry.get("name")
        if name is not None:
            if not isinstance(name, str) or not name.strip():
                raise ConfigError(f"{path}: {key!r} name must be text")
            if "/" in name or any(c in name for c in FORBIDDEN_TOPIC_CHARACTERS):
                raise ConfigError(f"{path}: {key!r} name must not contain /, + or #")
            name = name.strip()
        limits: dict[str, tuple[float, float]] = {}
        for prop, pair in (entry.get("limits") or {}).items():
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in pair)
                or pair[0] >= pair[1]
            ):
                raise ConfigError(f"{path}: {key!r} limit {prop!r} must be [low, high]")
            limits[prop] = (float(pair[0]), float(pair[1]))
        exclude = entry.get("exclude") or []
        if not isinstance(exclude, list) or not all(isinstance(n, str) for n in exclude):
            raise ConfigError(f"{path}: {key!r} exclude must be a list of property names")
        step = entry.get("step")
        if step is not None and (
            not isinstance(step, (int, float)) or isinstance(step, bool) or step <= 0
        ):
            raise ConfigError(f"{path}: {key!r} step must be a positive number")
        unknown = set(entry) - {"name", "limits", "exclude", "step"}
        if unknown:
            raise ConfigError(f"{path}: {key!r} has unknown keys: {', '.join(sorted(unknown))}")
        devices[key] = DeviceOptions(
            name=name,
            limits=limits,
            exclude=frozenset(exclude),
            step=float(step) if step is not None else None,
        )
    return devices


def load(env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    username = _text(env, "MQTT_USERNAME")
    password = env.get("MQTT_PASSWORD", "")
    if password and not username:
        raise ConfigError("MQTT_USERNAME is required when MQTT_PASSWORD is set")
    bridge_name = _text(env, "BRIDGE_NAME", "homekit-mqtt")
    if "/" in bridge_name or any(c in bridge_name for c in FORBIDDEN_TOPIC_CHARACTERS):
        raise ConfigError("BRIDGE_NAME must not contain /, + or #")
    data_dir = Path(_text(env, "HOMEKIT_DATA_DIR", "/data"))
    return Config(
        mqtt_host=_required(env, "MQTT_HOST"),
        mqtt_port=_int(env, "MQTT_PORT", "1883", 1, 65535),
        mqtt_username=username,
        mqtt_password=password,
        mqtt_tls=_bool(env, "MQTT_TLS_ENABLED", "false"),
        mqtt_client_id=_text(env, "MQTT_CLIENT_ID", "homekit-mqtt"),
        base_topic=_topic("MQTT_BASE_TOPIC", _text(env, "MQTT_BASE_TOPIC", "homekit")),
        bridge_name=bridge_name,
        discovery_enabled=_bool(env, "HA_DISCOVERY_ENABLED", "true"),
        discovery_prefix=_topic(
            "HA_DISCOVERY_PREFIX", _text(env, "HA_DISCOVERY_PREFIX", "homeassistant")
        ),
        data_dir=data_dir,
        poll_interval=_int(env, "HOMEKIT_POLL_INTERVAL", "60", 10, 3600),
        include_vendor=_bool(env, "HOMEKIT_INCLUDE_VENDOR", "false"),
        devices=load_devices(data_dir / "devices.json"),
    )
