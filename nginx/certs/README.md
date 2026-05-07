# SSL/TLS certifikáty

Tato složka musí obsahovat:

```
cert.pem   — TLS certifikát (full-chain pro produkci)
key.pem    — privátní klíč
```

Oba soubory jsou v `.gitignore` — nikdy je necommituj.

## Interní pilot (self-signed)

```bash
# Pouze localhost
./scripts/generate-pilot-cert.sh

# + přístup přes LAN IP (např. z Qt klienta na jiném stroji)
./scripts/generate-pilot-cert.sh 192.168.1.50
```

Skript vygeneruje certifikát se správnými SAN rozšířeními (vyžadováno Chrome 58+,
Firefox, Edge — CN-only cert prohlížeče odmítají).

## Produkce (Let's Encrypt)

```bash
certbot certonly --standalone -d yourdomain.com
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/certs/cert.pem
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem   nginx/certs/key.pem
chmod 600 nginx/certs/key.pem
```
