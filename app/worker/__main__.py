from __future__ import annotations

import argparse

from app.worker.runner import run_worker


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.worker")
    parser.add_argument("command", choices=["run"])
    args = parser.parse_args()
    if args.command == "run":
        run_worker()


if __name__ == "__main__":
    main()
