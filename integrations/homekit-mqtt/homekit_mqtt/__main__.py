"""Run the HomeKit to MQTT bridge."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

import aiomqtt
from aiohomekit import Controller
from aiohomekit.characteristic_cache import CharacteristicCacheFile
from aiohomekit.zeroconf import ZeroconfServiceListener
from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

from . import cli
from . import config as settings
from .bridge import Bridge

LOG = logging.getLogger("homekit_mqtt")
PAIRING_WAIT = 60


class MqttPublisher:
    def __init__(self, client: aiomqtt.Client) -> None:
        self.client = client

    async def publish(self, topic: str, payload: str, retain: bool = True) -> None:
        await self.client.publish(topic, payload, qos=1, retain=retain)


def _online(online: bool) -> str:
    return json.dumps({"state": "online" if online else "offline"})


async def run_mqtt(cfg: settings.Config, bridge: Bridge) -> None:
    """Stay connected to the broker; republish everything after each connect."""
    prefix = f"{cfg.base_topic}/"
    delay = 5
    while True:
        try:
            async with aiomqtt.Client(
                hostname=cfg.mqtt_host,
                port=cfg.mqtt_port,
                username=cfg.mqtt_username or None,
                password=cfg.mqtt_password or None,
                identifier=cfg.mqtt_client_id,
                tls_params=aiomqtt.TLSParameters() if cfg.mqtt_tls else None,
                will=aiomqtt.Will(
                    cfg.bridge_availability_topic, _online(False), qos=1, retain=True
                ),
            ) as client:
                LOG.info("Connected to MQTT %s:%d", cfg.mqtt_host, cfg.mqtt_port)
                delay = 5
                publisher = MqttPublisher(client)
                await client.publish(cfg.bridge_availability_topic, _online(True), qos=1, retain=True)
                await client.subscribe(f"{cfg.base_topic}/+/set", qos=1)
                bridge.publisher = publisher
                bridge.everything_changed()
                try:
                    async for message in client.messages:
                        topic = str(message.topic)
                        if topic.startswith(prefix) and topic.endswith("/set"):
                            name = topic[len(prefix) : -len("/set")]
                            await bridge.handle_command(name, message.payload)
                except asyncio.CancelledError:
                    # A clean disconnect does not send the will, so say offline first.
                    bridge.publisher = None
                    await client.publish(
                        cfg.bridge_availability_topic, _online(False), qos=1, retain=True
                    )
                    raise
        except aiomqtt.MqttError as exc:
            bridge.publisher = None
            LOG.warning("MQTT connection lost (%s); reconnecting in %d s", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


async def wait_for_pairings(cfg: settings.Config) -> None:
    while True:
        try:
            pairings = json.loads(cfg.pairing_file.read_text(encoding="utf-8"))
            if pairings:
                return
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            LOG.error("%s cannot be read: %s", cfg.pairing_file, exc)
        LOG.info(
            "No paired accessories in %s yet; pair one (see README). Checking again in %d s.",
            cfg.pairing_file,
            PAIRING_WAIT,
        )
        await asyncio.sleep(PAIRING_WAIT)


async def serve(cfg: settings.Config) -> None:
    await wait_for_pairings(cfg)

    zeroconf = AsyncZeroconf()
    controller = Controller(
        async_zeroconf_instance=zeroconf,
        char_cache=CharacteristicCacheFile(cfg.charmap_file),
    )
    async with zeroconf:
        browser = AsyncServiceBrowser(
            zeroconf.zeroconf,
            ["_hap._tcp.local.", "_hap._udp.local."],
            listener=ZeroconfServiceListener(),
        )
        try:
            async with controller:
                controller.load_data(cfg.pairing_file)
                bridge = Bridge(cfg, controller)
                LOG.info("Pairings: %s", ", ".join(sorted(controller.aliases)))
                tasks = [
                    asyncio.create_task(bridge.add_pairing(alias, pairing))
                    for alias, pairing in controller.aliases.items()
                ]
                tasks += [
                    asyncio.create_task(run_mqtt(cfg, bridge)),
                    asyncio.create_task(bridge.publish_forever()),
                    asyncio.create_task(bridge.poll_forever()),
                ]
                try:
                    await asyncio.gather(*tasks)
                finally:
                    bridge.close()
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            await browser.async_cancel()


async def main() -> None:
    cfg = settings.load()
    service = asyncio.create_task(serve(cfg))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, service.cancel)
        except NotImplementedError:
            pass
    try:
        await service
    except asyncio.CancelledError:
        LOG.info("Stopped")


def entrypoint() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("aiohomekit").setLevel(logging.WARNING)
    if len(sys.argv) > 1:
        cli.run(sys.argv[1:], Path(os.environ.get("HOMEKIT_DATA_DIR", "/data")))
        return
    try:
        asyncio.run(main())
    except settings.ConfigError as exc:
        LOG.error("%s", exc)
        sys.exit(2)


if __name__ == "__main__":
    entrypoint()
