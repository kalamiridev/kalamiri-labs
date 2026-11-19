"""Find, pair and unpair HomeKit accessories.

The pairing keys are written to the pairing file in the data directory, which
the service reads at start.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import re
from pathlib import Path
from typing import AsyncIterator

from aiohomekit import Controller
from aiohomekit.characteristic_cache import CharacteristicCacheFile
from aiohomekit.exceptions import HomeKitException
from aiohomekit.zeroconf import ZeroconfServiceListener
from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

PIN = re.compile(r"^\d{3}-\d{2}-\d{3}$")


def read_pairings(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path} does not hold pairings")
    return data


def write_pairings(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


@contextlib.asynccontextmanager
async def controller(data_dir: Path, load: bool) -> AsyncIterator[Controller]:
    zeroconf = AsyncZeroconf()
    ctrl = Controller(
        async_zeroconf_instance=zeroconf,
        char_cache=CharacteristicCacheFile(data_dir / "charmap.json"),
    )
    async with zeroconf:
        browser = AsyncServiceBrowser(
            zeroconf.zeroconf,
            ["_hap._tcp.local.", "_hap._udp.local."],
            listener=ZeroconfServiceListener(),
        )
        try:
            async with ctrl:
                if load and (data_dir / "pairing.json").exists():
                    ctrl.load_data(data_dir / "pairing.json")
                yield ctrl
        finally:
            await browser.async_cancel()


async def discover(data_dir: Path, seconds: int) -> None:
    async with controller(data_dir, load=False) as ctrl:
        await asyncio.sleep(seconds)
        found = False
        async for discovery in ctrl.async_discover(seconds):
            found = True
            description = discovery.description
            paired = "paired" if discovery.paired else "not paired"
            model = getattr(description, "model", "")
            print(f"{description.id}  {description.name}  {model}  ({paired})")
        if not found:
            print("No HomeKit accessories found. Is the container on the host network?")


async def pair(data_dir: Path, device_id: str, pin: str, alias: str) -> None:
    if not PIN.match(pin):
        raise SystemExit("The setup code has the form 123-45-678")
    path = data_dir / "pairing.json"
    pairings = read_pairings(path)
    if alias in pairings:
        raise SystemExit(f"{alias!r} is already paired")
    async with controller(data_dir, load=False) as ctrl:
        try:
            discovery = await ctrl.async_find(device_id)
            finish = await discovery.async_start_pairing(alias)
            pairing = await finish(pin)
        except HomeKitException as exc:
            raise SystemExit(f"Pairing failed: {exc}") from exc
        pairings[alias] = pairing.pairing_data
        write_pairings(path, pairings)
        print(f"Paired {device_id} as {alias!r}. Restart the service to use it.")


async def unpair(data_dir: Path, alias: str) -> None:
    path = data_dir / "pairing.json"
    pairings = read_pairings(path)
    if alias not in pairings:
        raise SystemExit(f"{alias!r} is not paired")
    async with controller(data_dir, load=True) as ctrl:
        try:
            await ctrl.remove_pairing(alias)
        except HomeKitException as exc:
            print(f"The accessory did not confirm ({exc}); removing the local keys anyway.")
    pairings.pop(alias, None)
    write_pairings(path, pairings)
    print(f"Unpaired {alias!r}. Restart the service.")


def run(argv: list[str], data_dir: Path) -> None:
    parser = argparse.ArgumentParser(prog="python -m homekit_mqtt")
    commands = parser.add_subparsers(dest="command", required=True)
    find = commands.add_parser("discover", help="list HomeKit accessories on the network")
    find.add_argument("-t", "--seconds", type=int, default=10)
    add = commands.add_parser("pair", help="pair an accessory")
    add.add_argument("-d", "--device", required=True, help="device id from discover")
    add.add_argument("-p", "--pin", required=True, help="setup code, 123-45-678")
    add.add_argument("-a", "--alias", required=True, help="a short name for the pairing")
    remove = commands.add_parser("unpair", help="unpair an accessory")
    remove.add_argument("-a", "--alias", required=True)
    args = parser.parse_args(argv)

    if args.command == "discover":
        asyncio.run(discover(data_dir, args.seconds))
    elif args.command == "pair":
        asyncio.run(pair(data_dir, args.device, args.pin, args.alias))
    else:
        asyncio.run(unpair(data_dir, args.alias))
