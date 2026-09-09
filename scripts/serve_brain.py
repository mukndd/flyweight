"""Conservative local-only launcher. No service installation or persistent startup changes."""
import os

# Only child-process numerical thread limits; no global environment or PATH changes.
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("services.brain.app:app", host="127.0.0.1", port=8000, workers=1, access_log=False,
                ws_max_size=8192, ws_max_queue=4, ws_ping_interval=10, ws_ping_timeout=10,
                timeout_keep_alive=10, backlog=8)

