# SSL/TLS certifikáty

Tato složka musí obsahovat:

```
cert.pem   — TLS certifikát (full-chain pro produkci)
key.pem    — privátní klíč
```

## Produkce (Let's Encrypt / Certbot)

```bash
certbot certonly --standalone -d yourdomain.com
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/certs/cert.pem
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem   nginx/certs/key.pem
chmod 600 nginx/certs/key.pem
```

## Self-signed (lokální testování / staging)

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/key.pem \
  -out    nginx/certs/cert.pem \
  -subj "/CN=localhost"
```

## Důležité

- `key.pem` NESMÍ být commitován do git (`nginx/certs/*.pem` je v `.gitignore`)
- Obnov certifikát před expirací (Let's Encrypt: 90 dní)
