#!/usr/bin/env python3
"""Create or update an auth user for Jorge bots."""

from __future__ import annotations

import argparse
import asyncio
import sys

from bots.shared.auth_service import UserRole, get_auth_service


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or update a dashboard user")
    parser.add_argument("--email", required=True, help="User email")
    parser.add_argument("--password", required=True, help="User password")
    parser.add_argument("--name", default="Admin User", help="Display name")
    parser.add_argument(
        "--role",
        default="admin",
        choices=["admin", "agent", "viewer"],
        help="User role",
    )
    parser.add_argument(
        "--must-change-password",
        default="true",
        help="true/false, force password reset on first login for newly created users",
    )
    parser.add_argument(
        "--reset-password-if-exists",
        default="true",
        help="true/false, reset password when user already exists",
    )
    return parser.parse_args()


async def _main() -> int:
    args = _parse_args()
    auth = get_auth_service()

    role_map = {
        "admin": UserRole.ADMIN,
        "agent": UserRole.AGENT,
        "viewer": UserRole.VIEWER,
    }
    role = role_map[args.role]
    must_change_password = _parse_bool(args.must_change_password)
    reset_password_if_exists = _parse_bool(args.reset_password_if_exists)

    existing = await auth.get_user_by_email(args.email, include_password=True)
    if existing:
        if reset_password_if_exists:
            ok = await auth.change_password(existing.user_id, args.password)
            if not ok:
                print("ERROR: failed to reset password for existing user", file=sys.stderr)
                return 1
            print(f"UPDATED_PASSWORD email={args.email} user_id={existing.user_id}")
        else:
            print(f"EXISTS email={args.email} user_id={existing.user_id}")
        return 0

    created = await auth.create_user(
        email=args.email,
        password=args.password,
        name=args.name,
        role=role,
        must_change_password=must_change_password,
    )
    print(f"CREATED email={created.email} user_id={created.user_id} role={created.role.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
