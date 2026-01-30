#!/usr/bin/env python3
"""gRPC health check client for GLADyS services.

Calls GetHealth or GetHealthDetails on a service and returns JSON.
"""

import argparse
import json
import sys
from pathlib import Path

# Add gladys_client to sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src" / "lib" / "gladys_client"))

from gladys_client.health import check_health


def main():
    parser = argparse.ArgumentParser(description="Check gRPC health endpoints")
    parser.add_argument("--address", required=True, help="Service address (host:port)")
    parser.add_argument("--detailed", action="store_true", help="Get detailed health info")
    args = parser.parse_args()

    result = check_health(args.address, args.detailed)
    print(json.dumps(result))

    # Return non-zero if not healthy
    if result.get("status") != "HEALTHY":
        sys.exit(1)


if __name__ == "__main__":
    main()
