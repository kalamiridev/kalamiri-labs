"""Keep paired HomeKit accessories in sync with MQTT."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from aiohomekit.controller.abstract import AbstractController, AbstractPairing
from aiohomekit.model.characteristics import Characteristic

from .config import Config
from .discovery import discovery_messages
from .mapping import Device, build_devices, make_names_unique, plan_writes, state

LOG = logging.getLogger(__name__)

Key = tuple[str, int, int]  # alias, aid, iid


class Publisher(Protocol):
    async def publish(self, topic: str, payload: str, retain: bool = True) -> None: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _key(alias: str, char: Characteristic) -> Key:
    return alias, char.service.accessory.aid, char.iid


class Bridge:
    """HomeKit side of the service. MQTT reaches it through publish and handle_command."""

    def __init__(self, config: Config, controller: AbstractController) -> None:
        self.config = config
        self.controller = controller
        self.devices: dict[str, Device] = {}
        self.pairings: dict[str, AbstractPairing] = {}
        self.values: dict[Key, Any] = {}
        self.available: dict[str, bool | None] = {}
        self.last_seen: dict[str, str] = {}
        self.dirty: set[str] = set()
        self.discovery_dirty = True
        self.changed = asyncio.Event()
        self.publisher: Publisher | None = None
        self._stoppers: list[Callable[[], None]] = []

    # ------------------------------------------------------------------ devices

    def value_of(self, alias: str) -> Callable[[Characteristic], Any]:
        return lambda char: self.values.get(_key(alias, char))

    def _devices_of(self, alias: str) -> list[Device]:
        return [d for d in self.devices.values() if d.alias == alias]

    def _rebuild(self) -> None:
        devices: list[Device] = []
        for alias, pairing in sorted(self.pairings.items()):
            if pairing.accessories is None:
                continue
            devices.extend(
                build_devices(alias, pairing.accessories, self.config.devices, self.config.include_vendor)
            )
        for note in make_names_unique(devices):
            LOG.warning("Two accessories have the same name: %s", note)
        self.devices = {d.name: d for d in devices}
        self.dirty.update(self.devices)
        self.discovery_dirty = True
        self.changed.set()
        LOG.info(
            "Devices: %s",
            ", ".join(f"{d.name} ({len(d.props)} properties)" for d in devices) or "none",
        )

    def _mark(self, alias: str, aids: set[int] | None = None, seen: bool = True) -> None:
        now = _now()
        for device in self._devices_of(alias):
            if aids is None or device.aid in aids:
                self.dirty.add(device.name)
                if seen:
                    self.last_seen[device.key] = now
        self.changed.set()

    def _set_available(self, alias: str, available: bool) -> None:
        if self.available.get(alias) != available:
            LOG.info("%s is %s", alias, "available" if available else "unavailable")
            self.available[alias] = available
            self._mark(alias, seen=False)

    def _store(self, alias: str, data: dict[tuple[int, int], dict[str, Any]]) -> set[int]:
        aids = set()
        for (aid, iid), result in data.items():
            if "value" in result:
                self.values[(alias, aid, iid)] = result["value"]
                aids.add(aid)
        return aids

    # ------------------------------------------------------------------ HomeKit

    async def add_pairing(self, alias: str, pairing: AbstractPairing) -> None:
        """Read the accessories of a pairing, subscribe to events and start polling it."""
        self.pairings[alias] = pairing
        self.available[alias] = None
        delay = 10
        while True:
            try:
                await pairing.async_populate_accessories_state(force_update=True)
                break
            except Exception as exc:  # noqa: BLE001 - any failure means try again later
                LOG.warning("%s: cannot read accessories (%s); retrying in %d s", alias, exc, delay)
                self._set_available(alias, False)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 300)

        assert pairing.accessories is not None
        for accessory in pairing.accessories:
            for service in accessory.services:
                for char in service.characteristics:
                    if char.value is not None:
                        self.values[(alias, accessory.aid, char.iid)] = char.value

        def on_event(data: dict[tuple[int, int], dict[str, Any]]) -> None:
            aids = self._store(alias, data)
            if aids:
                self._set_available(alias, True)
                self._mark(alias, aids)

        def on_available(available: bool) -> None:
            self._set_available(alias, available)

        def on_config_changed(_config_num: int) -> None:
            LOG.info("%s changed its accessories; rebuilding devices", alias)
            self._rebuild()
            asyncio.get_running_loop().create_task(self._subscribe(alias))

        self._stoppers += [
            pairing.dispatcher_connect(on_event),
            pairing.dispatcher_availability_changed(on_available),
            pairing.dispatcher_connect_config_changed(on_config_changed),
        ]
        self._rebuild()
        await self._subscribe(alias)
        await self.poll(alias)

    async def _subscribe(self, alias: str) -> None:
        pairing = self.pairings[alias]
        chars = [
            (device.aid, char.iid)
            for device in self._devices_of(alias)
            for char in device.event_chars()
        ]
        if not chars:
            return
        try:
            await pairing.subscribe(chars)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("%s: subscribing to events failed (%s); polling only", alias, exc)

    async def poll(self, alias: str) -> None:
        """Read every readable characteristic of a pairing once."""
        pairing = self.pairings[alias]
        chars = sorted(
            {
                (device.aid, char.iid)
                for device in self._devices_of(alias)
                for char in device.readable_chars()
            }
        )
        if not chars:
            return
        try:
            data = await pairing.get_characteristics(chars)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("%s: reading failed (%s)", alias, exc)
            self._set_available(alias, False)
            return
        self._store(alias, data)
        self._set_available(alias, True)
        self._mark(alias)

    async def poll_forever(self) -> None:
        while True:
            await asyncio.sleep(self.config.poll_interval)
            await asyncio.gather(*(self.poll(alias) for alias in list(self.pairings)))

    def close(self) -> None:
        for stop in self._stoppers:
            stop()
        self._stoppers.clear()

    # ------------------------------------------------------------------ commands

    async def handle_command(self, name: str, payload: bytes | str) -> None:
        """Apply a command from <base>/<device>/set and publish the new state."""
        device = self.devices.get(name)
        if device is None:
            LOG.warning("Command for unknown device %r", name)
            return
        try:
            command = json.loads(payload)
        except (TypeError, ValueError):
            LOG.warning("%s: command is not JSON", name)
            return
        if not isinstance(command, dict) or not command:
            LOG.warning("%s: command must be a JSON object", name)
            return

        value_of = self.value_of(device.alias)
        batches, errors = plan_writes(device, command, value_of)
        for error in errors:
            LOG.warning("%s: %s", name, error)

        try:
            if len(batches) == 2:
                # A thermostat mode goes first: which setpoint is meant depends on it.
                await self._write(device, batches[0])
                batches = plan_writes(device, command, value_of)[0][1:]
            for batch in batches:
                await self._write(device, batch)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("%s: command failed (%s)", name, exc)

        # The state is published after every command, also when nothing changed,
        # so the sender sees the command answered.
        await self.poll(device.alias)
        self.dirty.add(device.name)
        await self.flush()

    async def _write(self, device: Device, batch: list[tuple[Characteristic, Any]]) -> None:
        pairing = self.pairings[device.alias]
        writes = [(char.service.accessory.aid, char.iid, raw) for char, raw in batch]
        results = await pairing.put_characteristics(writes) or {}
        for (aid, iid), result in results.items():
            LOG.warning(
                "%s: writing %d.%d failed: %s",
                device.name,
                aid,
                iid,
                result.get("description", result.get("status")),
            )
        for aid, iid, raw in writes:
            if (aid, iid) not in results:
                self.values[(device.alias, aid, iid)] = raw

    # ------------------------------------------------------------------ MQTT

    def device_topic(self, device: Device) -> str:
        return f"{self.config.base_topic}/{device.name}"

    async def flush(self) -> None:
        """Publish discovery and every changed device."""
        publisher = self.publisher
        if publisher is None:
            return
        if self.discovery_dirty and self.config.discovery_enabled:
            self.discovery_dirty = False
            for device in self.devices.values():
                for topic, config in discovery_messages(
                    device,
                    self.config.base_topic,
                    self.config.discovery_prefix,
                    self.config.bridge_availability_topic,
                ):
                    await publisher.publish(topic, json.dumps(config, ensure_ascii=False))
        names, self.dirty = self.dirty, set()
        for name in sorted(names):
            device = self.devices.get(name)
            if device is None:
                continue
            available = self.available.get(device.alias)
            topic = self.device_topic(device)
            if available is not None:
                await publisher.publish(
                    f"{topic}/availability",
                    json.dumps({"state": "online" if available else "offline"}),
                )
            message = state(device, self.value_of(device.alias))
            if not message:
                continue
            if device.key in self.last_seen:
                message["last_seen"] = self.last_seen[device.key]
            await publisher.publish(topic, json.dumps(message, ensure_ascii=False, allow_nan=False))

    async def publish_forever(self) -> None:
        while True:
            await self.changed.wait()
            self.changed.clear()
            await self.flush()

    def everything_changed(self) -> None:
        self.dirty.update(self.devices)
        self.discovery_dirty = True
        self.changed.set()
