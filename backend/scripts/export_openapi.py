"""Write the API's OpenAPI schema to a file (input for frontend type generation).

Usage (from backend/):
    uv run python -m scripts.export_openapi ../frontend/openapi.json
"""

import json
import sys
from pathlib import Path

from app.main import create_app


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    out.write_text(json.dumps(create_app().openapi(), indent=2) + "\n")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
