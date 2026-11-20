"""Device names that others on the base topic already have.

Zigbee2MQTT and the services of a gateway can share one base topic, where each device is <base>/<name>. Two
devices of one name would then share a state topic and both take its commands: turning one off would turn off
the other. The names in the gateway's own catalog (<base>/bridge/devices) and in the catalogs of the services
named before this one (<base>/<service>/bridge/devices, in ordinal order, the order in which a reader combines
them) keep their devices; a device of this service with such a name is left out until one of them is renamed.
"""

from __future__ import annotations

import json
import logging

LOG = logging.getLogger(__name__)
CATALOG = "bridge/devices"


class TakenNames:
    def __init__(self, base_topic: str, own: str) -> None:
        self.base_topic = base_topic
        self.own = own
        self._names: dict[str, set[str]] = {}  # source ("" for the gateway's own catalog) -> names

    @property
    def topics(self) -> list[str]:
        """The catalogs to subscribe to; they are retained, so they arrive right after subscribing."""
        return [f"{self.base_topic}/{CATALOG}", f"{self.base_topic}/+/{CATALOG}"]

    def source(self, topic: str) -> str | None:
        """"" for the gateway's own catalog, the service for a catalog of one before this service, else None."""
        prefix = f"{self.base_topic}/"
        if not topic.startswith(prefix):
            return None
        rest = topic[len(prefix) :]
        if rest == CATALOG:
            return ""
        service, _, catalog = rest.partition("/")
        if catalog != CATALOG or not service or service >= self.own:
            return None
        return service

    def apply(self, topic: str, payload: bytes | str) -> bool:
        """Take a catalog in; True when the names it holds changed. An empty payload removes the catalog."""
        source = self.source(topic)
        if source is None:
            return False
        names: set[str] = set()
        if payload:
            try:
                devices = json.loads(payload)
            except (TypeError, ValueError):
                LOG.warning("%s is not JSON; its names are kept as they were", topic)
                return False
            if not isinstance(devices, list):
                LOG.warning("%s is not a list of devices; its names are kept as they were", topic)
                return False
            names = {
                device["friendly_name"]
                for device in devices
                if isinstance(device, dict) and isinstance(device.get("friendly_name"), str)
            }
        if names == self._names.get(source, set()):
            return False
        if names:
            self._names[source] = names
        else:
            self._names.pop(source, None)
        return True

    def owner(self, name: str) -> str | None:
        """Who has the name: the catalog topic that lists it, or None when it is free."""
        for source in sorted(self._names):
            if name in self._names[source]:
                return f"{self.base_topic}/{source}/{CATALOG}" if source else f"{self.base_topic}/{CATALOG}"
        return None
