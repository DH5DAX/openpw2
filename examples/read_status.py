"""Read-only example. Run with host and user ID; the password is prompted."""

import argparse
import asyncio
import getpass
import json

from openpw2 import Client, ConnectionConfig


async def read(host, user):
    config = ConnectionConfig(host, user, getpass.getpass("PW2 password: "))
    async with Client(config, on_state=lambda state: print(json.dumps(state))) as client:
        await asyncio.sleep(10)
        print("Final status:", client.snapshot)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument("user")
    args = parser.parse_args()
    asyncio.run(read(args.host, args.user))
