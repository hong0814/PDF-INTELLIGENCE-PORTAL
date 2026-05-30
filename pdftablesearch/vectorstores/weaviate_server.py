"""Embedded Weaviate server entry point for local development."""

from __future__ import annotations

import signal
import time
from pathlib import Path
from typing import Any

from pdftablesearch.vectorstores.weaviate_client import get_weaviate_config
from pdftablesearch.utils import get_logger

logger = get_logger(__name__)


def _start_embedded_weaviate(config: dict[str, Any]) -> Any:
    """Start embedded Weaviate with explicit HTTP/gRPC ports."""
    import weaviate

    data_path = Path(config["data_dir"]).resolve()
    data_path.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Starting embedded Weaviate at %s:%d (gRPC %d), data=%s",
        config["host"],
        config["port"],
        config["grpc_port"],
        data_path,
    )
    return weaviate.connect_to_embedded(
        hostname=config["host"],
        port=config["port"],
        grpc_port=config["grpc_port"],
        persistence_data_path=str(data_path),
        environment_variables={
            "PORT": str(config["port"]),
            "GRPC_PORT": str(config["grpc_port"]),
            "CLUSTER_IN_LOCAL": "true",
            "CLUSTER_HOSTNAME": str(config["cluster_hostname"]),
        },
    )


def main() -> None:
    """Run embedded Weaviate until interrupted."""
    config = get_weaviate_config()
    client = _start_embedded_weaviate(config)
    should_stop = False

    def _handle_stop(_signum: int, _frame: object) -> None:
        nonlocal should_stop
        should_stop = True

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    logger.info("Embedded Weaviate is running")
    try:
        while not should_stop:
            time.sleep(0.5)
    finally:
        client.close()
        logger.info("Embedded Weaviate stopped")


if __name__ == "__main__":
    main()
