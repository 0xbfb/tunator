from __future__ import annotations

import argparse
import json

from app.core.vendor.tor_runtime_manager import TorRuntimeManager


def main() -> None:
    parser = argparse.ArgumentParser(prog="tunator-cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap-local-tor", help="Prepare project-local Tor runtime")
    bootstrap.add_argument("--archive", dest="archive", default=None, help="Path to an already downloaded tor expert bundle")
    bootstrap.add_argument("--download-if-missing", action="store_true", help="Download the official bundle if none is present locally")

    info = subparsers.add_parser("show-runtime", help="Show current local Tor runtime information")
    info.add_argument("--json", action="store_true", help="Print JSON only")

    args = parser.parse_args()
    runtime = TorRuntimeManager()

    if args.command == "bootstrap-local-tor":
        binary_path = runtime.bootstrap_local_tor(archive_path=args.archive, download_if_missing=args.download_if_missing)
        payload = runtime.bundle_status()
        payload["runtime_binary_path"] = str(binary_path) if binary_path else None
        print(json.dumps(payload, indent=2))
        return

    if args.command == "show-runtime":
        payload = runtime.bundle_status()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            for key, value in payload.items():
                print(f"{key}: {value}")


if __name__ == "__main__":
    main()
