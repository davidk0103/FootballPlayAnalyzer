"""User administration CLI.

    python -m app.auth create-admin --email you@example.com   # prompts for a password
    python -m app.auth promote --email you@example.com
    python -m app.auth demote --email you@example.com

The password can also come from the PLAYBOOKIQ_ADMIN_PASSWORD environment variable
(for CI and scripted setups); it is never accepted as a command-line argument, where it
would end up in shell history and process listings.
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from app.auth import service
from app.db import get_sessionmaker
from app.models import User
from app.services.errors import ConflictError, InvalidRequestError

PASSWORD_ENV = "PLAYBOOKIQ_ADMIN_PASSWORD"


def _password() -> str:
    from_env = os.environ.get(PASSWORD_ENV)
    if from_env:
        return from_env
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise InvalidRequestError("Passwords do not match")
    return first


def create_admin(email: str) -> str:
    with get_sessionmaker()() as s:
        address = service.normalize_email(email)
        existing = s.scalar(select(User).where(User.email == address))
        if existing is not None:
            service.set_admin(s, address, is_admin=True)
            return f"{address} already exists; granted admin"
        try:
            service.register(s, email=address, password=_password(), is_admin=True)
        except ConflictError:
            service.set_admin(s, address, is_admin=True)
        return f"created admin {address}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.auth")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("create-admin", "promote", "demote"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--email", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create-admin":
            print(create_admin(args.email))
        else:
            with get_sessionmaker()() as s:
                user = service.set_admin(s, args.email, is_admin=args.command == "promote")
            print(f"{user.email}: is_admin={user.is_admin}")
    except InvalidRequestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
