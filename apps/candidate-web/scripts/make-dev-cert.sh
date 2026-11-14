#!/usr/bin/env bash
# 生成本地开发用的 HTTPS 证书。
#
# 手机通过局域网 IP 打开候选人端时，http:// 不是安全上下文，浏览器会把
# navigator.mediaDevices 直接藏起来，麦克风必然开不了。用这里的证书跑
# vite 的 https 后，手机访问 https://<本机IP>:5175 才能录音。
#
# 用法：./scripts/make-dev-cert.sh [本机局域网IP]
# 换网络（热点重连换了 IP）后重跑一次即可。
set -euo pipefail

IP="${1:-$(hostname -I | awk '{print $1}')}"
DIR="$(cd "$(dirname "$0")/.." && pwd)/.certs"
mkdir -p "$DIR"
cd "$DIR"

if [ ! -f ca-key.pem ]; then
  openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
    -keyout ca-key.pem -out ca-cert.pem -subj "/CN=TTC Dev CA"
fi

cat > leaf.ext <<EOF
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:${IP},IP:127.0.0.1,DNS:localhost
EOF

openssl req -newkey rsa:2048 -sha256 -nodes -keyout dev-key.pem -out leaf.csr \
  -subj "/CN=${IP}"
openssl x509 -req -in leaf.csr -CA ca-cert.pem -CAkey ca-key.pem -CAcreateserial \
  -days 825 -sha256 -extfile leaf.ext -out dev-cert.pem
rm -f leaf.csr leaf.ext

echo "证书已生成：$DIR/dev-cert.pem"
echo "CA 证书：$DIR/ca-cert.pem（手机需要信任它，见 README「手机上录音」）"
echo "手机访问：https://${IP}:5175"
