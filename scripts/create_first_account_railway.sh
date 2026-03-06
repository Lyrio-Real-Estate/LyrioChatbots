#!/usr/bin/env bash
set -euo pipefail

# Create/update first dashboard account on Railway by running inside a service container.
#
# Usage:
#   bash scripts/create_first_account_railway.sh --email you@example.com --password 'StrongPass123!'
#
# Optional:
#   --name "Jorge Admin"
#   --role admin|agent|viewer              (default: admin)
#   --service lead-bot                      (default: lead-bot)
#   --must-change-password true|false       (default: true for new users)
#   --reset-password-if-exists true|false   (default: true)

SERVICE="lead-bot"
EMAIL=""
PASSWORD=""
NAME="Admin User"
ROLE="admin"
MUST_CHANGE_PASSWORD="true"
RESET_PASSWORD_IF_EXISTS="true"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service)
      SERVICE="${2:-}"; shift 2 ;;
    --email)
      EMAIL="${2:-}"; shift 2 ;;
    --password)
      PASSWORD="${2:-}"; shift 2 ;;
    --name)
      NAME="${2:-}"; shift 2 ;;
    --role)
      ROLE="${2:-}"; shift 2 ;;
    --must-change-password)
      MUST_CHANGE_PASSWORD="${2:-}"; shift 2 ;;
    --reset-password-if-exists)
      RESET_PASSWORD_IF_EXISTS="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '1,40p' "$0"
      exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1 ;;
  esac
done

if [[ -z "${EMAIL}" || -z "${PASSWORD}" ]]; then
  echo "Missing required args. Use: --email and --password" >&2
  exit 1
fi

if [[ ! "${ROLE}" =~ ^(admin|agent|viewer)$ ]]; then
  echo "Invalid role: ${ROLE}. Use admin|agent|viewer" >&2
  exit 1
fi

printf -v EMAIL_Q '%q' "${EMAIL}"
printf -v PASSWORD_Q '%q' "${PASSWORD}"
printf -v NAME_Q '%q' "${NAME}"
printf -v ROLE_Q '%q' "${ROLE}"
printf -v MUST_Q '%q' "${MUST_CHANGE_PASSWORD}"
printf -v RESET_Q '%q' "${RESET_PASSWORD_IF_EXISTS}"

echo "Running account setup in Railway service: ${SERVICE}"
railway ssh -s "${SERVICE}" "EMAIL=${EMAIL_Q} PASSWORD=${PASSWORD_Q} NAME=${NAME_Q} ROLE=${ROLE_Q} MUST_CHANGE_PASSWORD=${MUST_Q} RESET_PASSWORD_IF_EXISTS=${RESET_Q} python -" <<'PY'
import asyncio
import os
import sys

from bots.shared.auth_service import UserRole, get_auth_service


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


async def main() -> int:
    email = os.environ["EMAIL"]
    password = os.environ["PASSWORD"]
    name = os.environ["NAME"]
    role_raw = os.environ["ROLE"]
    must_change = parse_bool(os.environ["MUST_CHANGE_PASSWORD"])
    reset_if_exists = parse_bool(os.environ["RESET_PASSWORD_IF_EXISTS"])

    role_map = {
        "admin": UserRole.ADMIN,
        "agent": UserRole.AGENT,
        "viewer": UserRole.VIEWER,
    }
    role = role_map[role_raw]

    auth = get_auth_service()
    existing = await auth.get_user_by_email(email, include_password=True)
    if existing:
        if reset_if_exists:
            ok = await auth.change_password(existing.user_id, password)
            if not ok:
                print("ERROR: failed to reset password for existing user", file=sys.stderr)
                return 1
            print(f"UPDATED_PASSWORD email={email} user_id={existing.user_id}")
        else:
            print(f"EXISTS email={email} user_id={existing.user_id}")
        return 0

    created = await auth.create_user(
        email=email,
        password=password,
        name=name,
        role=role,
        must_change_password=must_change,
    )
    print(f"CREATED email={created.email} user_id={created.user_id} role={created.role.value}")
    return 0


raise SystemExit(asyncio.run(main()))
PY
