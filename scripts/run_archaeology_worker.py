#!/usr/bin/env python3
from __future__ import annotations

import argparse

from ami_knowledge_core.migrate import apply_migrations
from ami_knowledge_core.worker import discover_jobs, run_worker


def main() -> int:
    parser = argparse.ArgumentParser(description="Run continuous archaeology worker v0.1")
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--batch-id", default="archaeology_batch_001")
    parser.add_argument("--queue-limit", type=int, default=20)
    args = parser.parse_args()

    if args.migrate:
        apply_migrations()
    if args.discover:
        created = discover_jobs(batch_id=args.batch_id)
        print(f"discovered_jobs={created}")
    report = run_worker(queue_limit=args.queue_limit)
    print(report)
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

