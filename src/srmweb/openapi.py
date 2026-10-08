"""Write the OpenAPI document: python -m srmweb.openapi [path]."""
import json
import sys
import tempfile
from pathlib import Path

from srmweb.api import create_app
from srmweb.config import load_settings

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "web" / "openapi.json"


def main(argv: list[str]) -> None:
    path = Path(argv[0]) if argv else DEFAULT_PATH
    with tempfile.TemporaryDirectory() as tmp:
        settings = load_settings({"SRMWEB_DB": str(Path(tmp) / "openapi.db")})
        spec = create_app(settings).openapi()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
