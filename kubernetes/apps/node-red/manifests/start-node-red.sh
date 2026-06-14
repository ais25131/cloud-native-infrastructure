#!/bin/sh
set -e

. /vault/secrets/node-red.env

mkdir -p /tmp/node-red-data
cp /config/flows.json /tmp/node-red-data/flows.json

cat > /tmp/node-red-data/flows_cred.json <<EOF
{
  "d329961bc35eeaf9": {
    "accesskeyid": "$MINIO_ACCESS_KEY",
    "secretaccesskey": "$MINIO_SECRET_KEY"
  },
  "7bfec4c89afd5431": {
    "user": "$RABBITMQ_USER",
    "password": "$RABBITMQ_PASSWORD"
  }
}
EOF

npm start -- --userDir /tmp/node-red-data