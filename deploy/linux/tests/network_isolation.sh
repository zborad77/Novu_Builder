#!/bin/sh
# Network isolation acceptance (WG_NETWORK_DESIGN.md §7, scenarios N1–N12).
# Run on STAGING from each vantage point; never needs credentials.
#
#   VANTAGE=internet  CORE=203.0.113.10 EDGE=203.0.113.11 sh network_isolation.sh
#   VANTAGE=edge                                          sh network_isolation.sh   # on the edge server (variant A)
#   VANTAGE=desktop-peer                                  sh network_isolation.sh   # inside a desktop tunnel
#   VANTAGE=admin-peer                                    sh network_isolation.sh   # inside an admin tunnel
#   VANTAGE=core                                          sh network_isolation.sh   # on the core server
#
# Single-server pilot: CORE and EDGE are the same address.
# Requires: nc (openbsd), curl. Exit code 1 if any expectation fails.
set -u
CORE_WG=10.50.0.1
CORE_ADMIN_WG=10.51.0.1
T=3
fail=0

open_tcp()   { nc -z -w "$T" "$1" "$2" >/dev/null 2>&1; }
expect_open()   { if open_tcp "$1" "$2"; then echo "OK   $3"; else echo "FAIL $3"; fail=1; fi; }
expect_closed() { if open_tcp "$1" "$2"; then echo "FAIL $3"; fail=1; else echo "OK   $3"; fi; }
expect_status() {  # URL STATUS LABEL [extra curl args]
  url=$1; want=$2; label=$3; shift 3
  got=$(curl -s -o /dev/null -w '%{http_code}' --max-time "$T" "$@" "$url" || echo 000)
  if [ "$got" = "$want" ]; then echo "OK   $label ($got)"; else echo "FAIL $label (got $got, want $want)"; fail=1; fi
}

case "${VANTAGE:?set VANTAGE}" in
  internet)
    : "${CORE:?set CORE}" "${EDGE:?set EDGE}"
    # N1/N2: only 80/443 on the edge; no TCP service on the core besides that edge role.
    for port in 22 5432 6379 8000 8200 8210 8220 9000 9001 9100; do
      expect_closed "$CORE" "$port" "N1 core public tcp/$port closed"
    done
    expect_open "$EDGE" 443 "N2 edge https open"
    expect_status "https://$EDGE/api/v1/auth/login" 404 "N2 edge does not expose the API" -k -X POST
    expect_status "https://$EDGE/api/v1/admin/users" 404 "N2 edge does not expose admin" -k
    ;;
  edge)
    # N3: edge cannot reach core desktop/admin/data ports over WireGuard.
    for port in 8210 8220 5432 6379 9000 22; do
      expect_closed "$CORE_WG" "$port" "N3 edge → core $port blocked"
    done
    # N11: edge has no general egress.
    expect_status "https://example.com/" 000 "N11 edge general egress blocked"
    ;;
  desktop-peer)
    # N4/N5/N7: desktop zone only.
    expect_status "http://$CORE_WG:8210/api/v1/health" 200 "N4 desktop zone reachable"
    expect_status "http://$CORE_WG:8210/api/v1/admin/users" 404 "N4 admin routes absent in desktop zone"
    expect_status "http://$CORE_WG:8210/api/v1/metrics" 404 "N4 metrics absent in desktop zone"
    expect_closed "$CORE_WG" 8200 "N5 gateway port blocked for desktop peers"
    expect_closed "$CORE_ADMIN_WG" 8220 "N5 admin zone blocked for desktop peers"
    expect_closed "$CORE_WG" 22 "N5 SSH blocked for desktop peers"
    for port in 5432 6379 9000; do expect_closed "$CORE_WG" "$port" "N5 data service $port blocked"; done
    # N6: no peer-to-peer traffic (another desktop address).
    expect_closed "10.50.16.11" 445 "N6 no routing to other desktop peers"
    ;;
  admin-peer)
    # N9: admin zone and SSH only through the admin tunnel.
    expect_open "$CORE_ADMIN_WG" 22 "N9 SSH via admin tunnel"
    expect_status "http://$CORE_ADMIN_WG:8220/api/v1/alive" 200 "N9 admin zone reachable"
    expect_status "http://$CORE_ADMIN_WG:8220/api/v1/cases" 404 "N9 tenant routes absent in admin zone"
    ;;
  core)
    # N10: data services listen on loopback only; the application user has no
    # general egress (only the nftables allowlist).
    if ss -ltnH | awk '{print $4}' | grep -E ':(5432|6379|9000|9001)$' | grep -vqE '^(127\.0\.0\.1|\[::1\]):'; then
      echo "FAIL N10 a data service listens beyond loopback"; fail=1
    else
      echo "OK   N10 data services listen on loopback only"
    fi
    if runuser -u novuconstruct -- curl -s -o /dev/null --max-time "$T" https://example.com/; then
      echo "FAIL N10 application user reached an arbitrary host"; fail=1
    else
      echo "OK   N10 application egress limited to the allowlist"
    fi
    # API sockets exist, are not TCP, and are not world-accessible.
    for zone in desktop admin; do
      sock=/run/novuconstruct/$zone/api.sock
      if [ -S "$sock" ] && [ "$(stat -c '%a' "$sock" | cut -c3)" = "0" ]; then
        echo "OK   N12 $zone API on private unix socket"
      else
        echo "FAIL N12 $zone API socket missing or world-accessible"; fail=1
      fi
    done
    ;;
  *) echo "unknown VANTAGE" >&2; exit 2 ;;
esac

[ "$fail" -eq 0 ] && echo "ISOLATION CHECKS PASSED ($VANTAGE)" || { echo "ISOLATION CHECKS FAILED ($VANTAGE)"; exit 1; }
