import json
from pathlib import Path

from aiohomekit.model import Accessories

FIXTURES = Path(__file__).parent / "fixtures"


def accessories(name: str) -> Accessories:
    return Accessories.from_list(json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")))


def current(char):
    return char.value
