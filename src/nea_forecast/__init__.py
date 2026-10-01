import json
from pathlib import Path

SOURCES_JSON = Path(__file__).resolve().parents[2] / "sources.json"


def load_sources() -> dict:
    """Source registry keyed by id."""
    return {s["id"]: s for s in json.loads(SOURCES_JSON.read_text())}
