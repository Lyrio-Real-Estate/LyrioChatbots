#!/usr/bin/env bash
set -euo pipefail

# Direct chat tester for seller/buyer bots (JWT-protected endpoints).
#
# Usage:
#   bash scripts/chat_bots_direct.sh
#
# Optional env overrides:
#   LOCATION_ID=4YAQhK8tcmFPyt2zzsJZ
#   SELLER_URL=http://localhost:8002
#   BUYER_URL=http://localhost:8003
#   AUTH_EMAIL=you@example.com
#   AUTH_PASSWORD=StrongPass123!
#   AUTH_TOKEN=<existing_jwt>                 # skip token generation if provided
#   AUTH_CONTAINER=lead-bot                   # docker compose service used to mint token
#   SELLER_ID=demo-seller-123
#   BUYER_ID=demo-buyer-123
#   SLEEP_SECONDS=0

LOCATION_ID="${LOCATION_ID:-4YAQhK8tcmFPyt2zzsJZ}"
SELLER_URL="${SELLER_URL:-http://localhost:8002}"
BUYER_URL="${BUYER_URL:-http://localhost:8003}"
AUTH_EMAIL="${AUTH_EMAIL:-bottester@example.com}"
AUTH_PASSWORD="${AUTH_PASSWORD:-ChangeMe123!}"
AUTH_TOKEN="${AUTH_TOKEN:-}"
AUTH_CONTAINER="${AUTH_CONTAINER:-lead-bot}"
SLEEP_SECONDS="${SLEEP_SECONDS:-0}"

STAMP="$(date +%s)"
SELLER_ID="${SELLER_ID:-direct-seller-${STAMP}}"
BUYER_ID="${BUYER_ID:-direct-buyer-${STAMP}}"

print_json() {
  local raw="$1"
  if command -v jq >/dev/null 2>&1; then
    if echo "${raw}" | jq . >/dev/null 2>&1; then
      echo "${raw}" | jq .
    else
      echo "${raw}"
    fi
  else
    echo "${raw}"
  fi
}

mint_token() {
  docker compose exec -T \
    -e AUTH_EMAIL="${AUTH_EMAIL}" \
    -e AUTH_PASSWORD="${AUTH_PASSWORD}" \
    "${AUTH_CONTAINER}" \
    python - <<'PY'
import asyncio
import os
import sys

from bots.shared.auth_service import UserRole, get_auth_service

email = os.environ["AUTH_EMAIL"]
password = os.environ["AUTH_PASSWORD"]

async def main() -> int:
    auth = get_auth_service()
    user = await auth.get_user_by_email(email)
    if not user:
        await auth.create_user(
            email=email,
            password=password,
            name="Bot Tester",
            role=UserRole.ADMIN,
        )
    tokens = await auth.authenticate(email, password)
    if not tokens:
        print("ERROR: failed to authenticate user", file=sys.stderr)
        return 1
    print(tokens.access_token)
    return 0

raise SystemExit(asyncio.run(main()))
PY
}

post_turn() {
  local url="$1"
  local contact_id="$2"
  local message="$3"
  local name="$4"
  local email="$5"
  local phone="$6"

  local payload
  payload="$(
    python3 - "$contact_id" "$LOCATION_ID" "$message" "$name" "$email" "$phone" <<'PY'
import json
import sys

contact_id, location_id, message, name, email, phone = sys.argv[1:7]
print(json.dumps({
    "contact_id": contact_id,
    "location_id": location_id,
    "message": message,
    "contact_info": {
        "name": name,
        "email": email,
        "phone": phone,
    },
}))
PY
  )"

  curl -sS -X POST "${url}" \
    -H "Authorization: Bearer ${AUTH_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "${payload}"
}

if [[ -z "${AUTH_TOKEN}" ]]; then
  echo "Minting JWT via docker compose service: ${AUTH_CONTAINER}"
  AUTH_TOKEN="$(
    mint_token \
      | tr -d '\r' \
      | grep -E '^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$' \
      | tail -n1
  )"
fi

if [[ -z "${AUTH_TOKEN}" ]]; then
  echo "Failed to obtain auth token." >&2
  exit 1
fi

echo "Seller URL: ${SELLER_URL}"
echo "Buyer URL: ${BUYER_URL}"
echo "Location: ${LOCATION_ID}"
echo "Auth User: ${AUTH_EMAIL}"
echo "Seller ID: ${SELLER_ID}"
echo "Buyer ID: ${BUYER_ID}"
echo

echo "== Seller Direct Chat =="
resp="$(post_turn "${SELLER_URL}/api/jorge-seller/process" "${SELLER_ID}" "I need to sell fast." "Direct Seller" "seller@example.com" "+15550001111")"
print_json "${resp}"
sleep "${SLEEP_SECONDS}"

resp="$(post_turn "${SELLER_URL}/api/jorge-seller/process" "${SELLER_ID}" "It is a 4 bed in Ontario, maybe worth 650k." "Direct Seller" "seller@example.com" "+15550001111")"
print_json "${resp}"
sleep "${SLEEP_SECONDS}"

resp="$(post_turn "${SELLER_URL}/api/jorge-seller/process" "${SELLER_ID}" "Need to move in about 45 days." "Direct Seller" "seller@example.com" "+15550001111")"
print_json "${resp}"
sleep "${SLEEP_SECONDS}"

echo
echo "== Buyer Direct Chat =="
resp="$(post_turn "${BUYER_URL}/api/jorge-buyer/process" "${BUYER_ID}" "Looking for a 3 bed under 700k in Rancho Cucamonga." "Direct Buyer" "buyer@example.com" "+15550002222")"
print_json "${resp}"
sleep "${SLEEP_SECONDS}"

resp="$(post_turn "${BUYER_URL}/api/jorge-buyer/process" "${BUYER_ID}" "Pre-approved and can close in 45 days." "Direct Buyer" "buyer@example.com" "+15550002222")"
print_json "${resp}"
sleep "${SLEEP_SECONDS}"

resp="$(post_turn "${BUYER_URL}/api/jorge-buyer/process" "${BUYER_ID}" "Need at least 2 bathrooms and 1800 sqft." "Direct Buyer" "buyer@example.com" "+15550002222")"
print_json "${resp}"

echo
echo "Done."
