#!/usr/bin/env bash
set -euo pipefail

# Multi-turn webhook tester for local Lead/Seller/Buyer bot routing.
#
# Usage:
#   bash scripts/chat_bots_webhook.sh
#
# Optional env overrides:
#   BASE_URL=http://localhost:8001
#   LOCATION_ID=4YAQhK8tcmFPyt2zzsJZ
#   BUYER_ID=demo-buyer-123
#   SELLER_ID=demo-seller-123
#   LEAD_ID=demo-lead-123
#   SLEEP_SECONDS=0

BASE_URL="${BASE_URL:-http://localhost:8001}"
LOCATION_ID="${LOCATION_ID:-4YAQhK8tcmFPyt2zzsJZ}"
SLEEP_SECONDS="${SLEEP_SECONDS:-0}"
STAMP="$(date +%s)"

BUYER_ID="${BUYER_ID:-demo-buyer-${STAMP}}"
SELLER_ID="${SELLER_ID:-demo-seller-${STAMP}}"
LEAD_ID="${LEAD_ID:-demo-lead-${STAMP}}"

print_json() {
  local raw="$1"
  if command -v jq >/dev/null 2>&1; then
    echo "${raw}" | jq .
  else
    echo "${raw}"
  fi
}

post_webhook() {
  local contact_id="$1"
  local bot_type="$2"
  local message="$3"
  local full_name="$4"
  local email="$5"
  local phone="$6"

  local payload
  payload="$(
    python3 - "$contact_id" "$bot_type" "$message" "$full_name" "$email" "$phone" "$LOCATION_ID" <<'PY'
import json
import sys

contact_id, bot_type, message, full_name, email, phone, location_id = sys.argv[1:8]
print(json.dumps({
    "contactId": contact_id,
    "locationId": location_id,
    "body": message,
    "bot_type": bot_type,
    "fullName": full_name,
    "email": email,
    "phone": phone,
}))
PY
  )"

  curl -sS -X POST "${BASE_URL}/api/ghl/webhook" \
    -H "Content-Type: application/json" \
    -d "${payload}"
}

echo "Base URL: ${BASE_URL}"
echo "Location: ${LOCATION_ID}"
echo "Buyer ID: ${BUYER_ID}"
echo "Seller ID: ${SELLER_ID}"
echo "Lead ID: ${LEAD_ID}"
echo

echo "== Seller turns =="
resp="$(post_webhook "${SELLER_ID}" "seller" "I need to sell my house in 30 days." "Demo Seller" "seller@example.com" "+15550001111")"
print_json "${resp}"
sleep "${SLEEP_SECONDS}"

resp="$(post_webhook "${SELLER_ID}" "seller" "The house is a 4 bed 3 bath in Ontario." "Demo Seller" "seller@example.com" "+15550001111")"
print_json "${resp}"
sleep "${SLEEP_SECONDS}"

resp="$(post_webhook "${SELLER_ID}" "seller" "I owe about 350k and want speed." "Demo Seller" "seller@example.com" "+15550001111")"
print_json "${resp}"
sleep "${SLEEP_SECONDS}"

echo
echo "== Buyer turns =="
resp="$(post_webhook "${BUYER_ID}" "buyer" "I want a 3 bed in Rancho Cucamonga under 700k." "Demo Buyer" "buyer@example.com" "+15550002222")"
print_json "${resp}"
sleep "${SLEEP_SECONDS}"

resp="$(post_webhook "${BUYER_ID}" "buyer" "I am pre approved and can close in 45 days." "Demo Buyer" "buyer@example.com" "+15550002222")"
print_json "${resp}"
sleep "${SLEEP_SECONDS}"

resp="$(post_webhook "${BUYER_ID}" "buyer" "Need at least 2 baths and 1800 sqft." "Demo Buyer" "buyer@example.com" "+15550002222")"
print_json "${resp}"
sleep "${SLEEP_SECONDS}"

echo
echo "== Lead turns =="
resp="$(post_webhook "${LEAD_ID}" "lead" "Thinking about buying this summer." "Demo Lead" "lead@example.com" "+15550003333")"
print_json "${resp}"
sleep "${SLEEP_SECONDS}"

resp="$(post_webhook "${LEAD_ID}" "lead" "Budget around 650k and already talking to lender." "Demo Lead" "lead@example.com" "+15550003333")"
print_json "${resp}"

echo
echo "Done."
