"""Bounded launcher. No service installation or persistent startup changes."""
import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"

import uvicorn  # noqa: E402

from services.brain.config import SETTINGS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def log_config():
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    handler = RotatingFileHandler(logs / "brain-runtime.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False


async def main():
    log_config()
    loop = asyncio.get_running_loop()
    def on_exception(loop, context):
        error = context.get("exception")
        # Windows reports normal peer TCP resets after browser socket closure.
        if isinstance(error, ConnectionResetError) and getattr(error, "winerror", None) == 10054:
            logging.getLogger("flyweight.transport").info("Peer closed transport")
            return
        loop.default_exception_handler(context)
    loop.set_exception_handler(on_exception)
    config = uvicorn.Config("services.brain.app:app", host=SETTINGS.host, port=SETTINGS.port, workers=1,
                            log_config=None, access_log=False, ws_max_size=8192, ws_max_queue=4,
                            ws_ping_interval=10, ws_ping_timeout=10, timeout_keep_alive=10,
                            timeout_graceful_shutdown=10, backlog=8)
    await uvicorn.Server(config).serve()


if __name__ == "__main__":
    asyncio.run(main())
