#!/usr/bin/env bash
# Run on the development machine, not on the 2 GB VPS. Build sequentially.
set -euo pipefail
cd "$(dirname "$0")/.."
tag="${1:-v1}"
[[ "$tag" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$ ]] || { echo 'Invalid image tag' >&2; exit 1; }
out="releases/$tag"
[[ ! -e "$out/SHA256SUMS" ]] || { echo 'Completed release already exists; choose a new tag' >&2; exit 1; }
mkdir -p "$out/deploy"
for component in backend frontend landing bot; do
  docker build --tag "irontech-$component:$tag" "$component"
done
docker pull caddy:2-alpine
docker pull postgres:17-alpine
docker save "irontech-backend:$tag" "irontech-frontend:$tag" "irontech-landing:$tag" "irontech-bot:$tag" caddy:2-alpine postgres:17-alpine | gzip > "$out/images.tar.gz.partial"
mv "$out/images.tar.gz.partial" "$out/images.tar.gz"
cp compose.production.yaml "$out/"
cp deploy/{Caddyfile,compose.sh,init-env.py,production.env.example,backup.sh,README.md} "$out/deploy/"
printf '%s\n' "$tag" > "$out/RELEASE_TAG"
(cd "$out" && sha256sum images.tar.gz > SHA256SUMS)
echo "Release prepared in $out. Set RELEASE_TAG=$tag in the server .env.production."
