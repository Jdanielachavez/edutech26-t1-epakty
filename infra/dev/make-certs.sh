#!/usr/bin/env bash
# Certificados SOLO para desarrollo local: una CA propia y un certificado para localhost.
# La base exige sslmode=verify-full, así que el cliente necesita la CA (certs/dev-ca.crt).
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p certs && cd certs
[ -f dev-ca.crt ] && [ -f dev-server.crt ] && { echo "certs/ ya tiene certificados de desarrollo"; exit 0; }
openssl req -x509 -newkey rsa:2048 -nodes -keyout dev-ca.key -out dev-ca.crt -days 90 -subj "/CN=E-Pakty Dev CA" 2>/dev/null
openssl req -newkey rsa:2048 -nodes -keyout dev-server.key -out dev-server.csr -subj "/CN=localhost" 2>/dev/null
printf "subjectAltName=DNS:localhost,IP:127.0.0.1\n" > dev-san.ext
openssl x509 -req -in dev-server.csr -CA dev-ca.crt -CAkey dev-ca.key -CAcreateserial -out dev-server.crt -days 90 -extfile dev-san.ext 2>/dev/null
rm -f dev-server.csr dev-san.ext dev-ca.srl
chmod 600 dev-ca.key dev-server.key
echo "Certificados de desarrollo creados en certs/ (válidos 90 días)"
