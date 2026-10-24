"""Start the local drift API: python -m infralens.backend --config projects.json."""

import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Local InfraLens drift API")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--database", type=Path, default=Path(".infralens/history.sqlite3")
    )
    parser.add_argument("--host", choices=["127.0.0.1", "::1"], default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--cors-origin", action="append", default=[])
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be from 1 to 65535")
    try:
        import uvicorn

        from infralens.backend.api import create_app
        from infralens.backend.config import Settings, load_projects

        settings = Settings(
            load_projects(args.config.resolve()),
            args.database.resolve(),
            os.environ.get("INFRALENS_API_TOKEN", ""),
            cors_origins=tuple(args.cors_origin),
        )
        app = create_app(settings)
        uvicorn.run(app, host=args.host, port=args.port, access_log=False)
        return 0
    except ImportError:
        print("Install the backend extra: pip install -e '.[backend]'", file=sys.stderr)
    except Exception:
        print(
            "Backend could not start. Check config, token, database and port.",
            file=sys.stderr,
        )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
