"""Child-process entry point: ``python -m worker.job_child <job_id> <lease_token>``.

Runs exactly one job attempt under the lease the parent worker claimed. The
parent supervises this process (heartbeat, cancellation, timeout) and kills
the whole tree when it must; nothing here needs to cooperate with that.
"""

from __future__ import annotations

import logging
import os
import sys


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: python -m worker.job_child <job_id> <lease_token>", file=sys.stderr)
        return 2
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

    from backend.job_runner import execute_job

    execute_job(args[0], args[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
