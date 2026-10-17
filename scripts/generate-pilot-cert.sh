#!/usr/bin/env bash
# Generate a self-signed TLS certificate for internal pilot deployment.
#
# Usage:
#   ./scripts/generate-pilot-cert.sh              # localhost + 127.0.0.1 only
#   ./scripts/generate-pilot-cert.sh 192.168.1.50 # + extra IP for LAN access
#
# Output: nginx/certs/cert.pem  nginx/certs/key.pem
#
# Requirements: openssl (available on any Linux/macOS/WSL host)
#
# NOTE: Modern browsers (Chrome 58+, Firefox, Edge) require Subject Alternative
# Name (SAN). A CN-only cert will be rejected even for localhost. This script
# always includes SAN entries.

set -euo pipefail

CERT_DIR="$(cd "$(dirname "$0")/.." && pwd)/nginx/certs"
EXTRA_IP="${1:-}"
DAYS=825   # max accepted by Apple/Chrome for internal certs

mkdir -p "$CERT_DIR"

# Build SAN list
SAN="IP:127.0.0.1,DNS:localhost"
if [[ -n "$EXTRA_IP" ]]; then
    SAN="${SAN},IP:${EXTRA_IP}"
    echo "→ Including extra IP in SAN: $EXTRA_IP"
fi

echo "→ Generating self-signed cert (${DAYS} days, SAN: ${SAN})"
echo "   Output: $CERT_DIR/{cert,key}.pem"

openssl req -x509 \
    -nodes \
    -days "$DAYS" \
    -newkey rsa:2048 \
    -keyout  "$CERT_DIR/key.pem" \
    -out     "$CERT_DIR/cert.pem" \
    -subj    "/O=NOVU Builder Internal/CN=novu-pilot" \
    -addext  "subjectAltName=${SAN}" \
    -addext  "basicConstraints=CA:FALSE" \
    -addext  "keyUsage=digitalSignature,keyEncipherment" \
    -addext  "extendedKeyUsage=serverAuth"

chmod 600 "$CERT_DIR/key.pem"
chmod 644 "$CERT_DIR/cert.pem"

echo ""
echo "✓ Certificate generated."
echo ""
echo "Validity : $(openssl x509 -noout -dates -in "$CERT_DIR/cert.pem" | grep notAfter | cut -d= -f2)"
echo "SAN      : $(openssl x509 -noout -ext subjectAltName -in "$CERT_DIR/cert.pem" | tail -1 | tr -d ' ')"
echo ""
echo "Next steps:"
echo "  1. docker compose up -d"
echo "  2. Accept the browser security warning once (internal pilot — expected)"
echo "  3. Optionally: install cert.pem in your OS/browser trust store to silence the warning"
echo ""
echo "To trust permanently on Linux:"
echo "  sudo cp $CERT_DIR/cert.pem /usr/local/share/ca-certificates/novu-pilot.crt"
echo "  sudo update-ca-certificates"
