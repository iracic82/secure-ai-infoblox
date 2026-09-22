#!/bin/bash
# Generate the DNS traffic the GenAI lab expects, from inside the VPC.
#
# Run this on the lab EC2 host (WebServerProdEu1) when the Flask app isn't
# driving queries. Resolves the gen-ai.csv Custom List domains (expected to be
# blocked), some trusted health domains (expected to resolve), and randomised
# exfiltration-style subdomains, so Security Events and the Threats dashboard
# populate in the Infoblox Portal.
#
# Usage:  bash generate_dns_traffic.sh [rounds] [resolver]
#   rounds   number of passes (default 3)
#   resolver DNS server to query (default: whatever /etc/resolv.conf says)

ROUNDS="${1:-3}"
RESOLVER="${2:-}"
DIG_OPTS="+time=2 +tries=1"
[ -n "$RESOLVER" ] && DIG_OPTS="$DIG_OPTS @$RESOLVER"

# Custom List entries from gen-ai.csv — these should come back NXDOMAIN.
BLOCKED=(
  "ai-medicine-data.com"
  "chunk1.ai-medicine-data.com"
  "login.ai-medicine-data.com"
  "api.ai-medicine-data.com"
  "suspicious-healthinfo.com"
  "chunk1.suspicious-healthinfo.com"
  "login.suspicious-healthinfo.com"
)

# Legitimate lookups, for contrast on the dashboard.
ALLOWED=(
  "webmd.com"
  "cdc.gov"
  "mayoclinic.org"
  "bedrock-runtime.eu-west-2.amazonaws.com"
)

# Parents used to build tunneling-style FQDNs.
EXFIL_PARENTS=("ai-medicine-data.com" "suspicious-healthinfo.com")

blocked_hits=0
allowed_hits=0
unexpected=0
no_answer=0

query() {
  # $1 = fqdn, $2 = expectation (blocked|allowed)
  local fqdn="$1" expect="$2" status
  status=$(dig $DIG_OPTS "$fqdn" 2>/dev/null | sed -n 's/.*status: \([A-Z]*\).*/\1/p' | head -1)

  if [ -z "$status" ]; then
    echo "   ⁉️  $fqdn — no response from resolver"
    no_answer=$((no_answer + 1))
    return
  fi

  case "$expect:$status" in
    blocked:NXDOMAIN)
      echo "   🛡️  $fqdn — NXDOMAIN (blocked)"
      blocked_hits=$((blocked_hits + 1)) ;;
    allowed:NOERROR)
      echo "   ✅  $fqdn — resolved"
      allowed_hits=$((allowed_hits + 1)) ;;
    *)
      echo "   ⚠️  $fqdn — $status (expected $expect)"
      unexpected=$((unexpected + 1)) ;;
  esac
}

echo "=== DNS traffic generator ==="
echo "Resolver: ${RESOLVER:-$(awk '/^nameserver/ {print $2; exit}' /etc/resolv.conf)}"
echo "Rounds:   $ROUNDS"
echo

# Fail fast rather than printing dozens of timeouts if the tunnel is down.
if ! dig $DIG_OPTS google.com >/dev/null 2>&1; then
  echo "❌ Resolver is not answering. Check the VPN tunnel and route propagation"
  echo "   before generating traffic."
  exit 1
fi

for round in $(seq 1 "$ROUNDS"); do
  echo "--- round $round/$ROUNDS ---"

  for d in "${BLOCKED[@]}"; do query "$d" blocked; done
  for d in "${ALLOWED[@]}"; do query "$d" allowed; done

  # Tunneling pattern: high-entropy labels under a listed parent.
  for i in 1 2 3; do
    label=$(head -c 48 /dev/urandom | base64 | tr -dc 'a-z0-9' | head -c 20)
    parent=${EXFIL_PARENTS[$((RANDOM % ${#EXFIL_PARENTS[@]}))]}
    query "${label}.${parent}" blocked
  done

  echo
  [ "$round" -lt "$ROUNDS" ] && sleep 2
done

echo "=== Summary ==="
echo "🛡️  Blocked as expected : $blocked_hits"
echo "✅  Resolved as expected: $allowed_hits"
echo "⚠️  Unexpected status   : $unexpected"
echo "⁉️  No response         : $no_answer"
echo
if [ "$blocked_hits" -eq 0 ]; then
  echo "No blocks recorded. Check that the Custom List 'Gen AI Policy List' is imported"
  echo "and that your security policy is applied to the NIOS-X-as-a-Service deployment."
else
  echo "Now check the Infoblox Portal:"
  echo "  Security → Threat Defense → Security Activity → Security Events"
  echo "  Dashboard → Security: Threats"
  echo "Allow a few minutes for events to propagate."
fi
