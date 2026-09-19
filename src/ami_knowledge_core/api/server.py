"""Uvicorn entrypoint for AMI Knowledge Core web/API service."""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    host = os.environ.get("KC_BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("KC_BIND_PORT", "8765"))
    uvicorn.run(
        "ami_knowledge_core.api.app:app",
        host=host,
        port=port,
        reload=os.environ.get("KC_RELOAD", "0") == "1",
    )


if __name__ == "__main__":
    main()

