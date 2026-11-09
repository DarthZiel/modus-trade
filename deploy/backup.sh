#!/usr/bin/env bash
# Briefly stop writers for a consistent database + attachment backup.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
compose=(./deploy/compose.sh)
mkdir -p backups
exec 9>backups/.lock
flock -n 9 || { echo 'Another backup is running' >&2; exit 1; }
mapfile -t writers < <("${compose[@]}" ps --services --status running | awk '/^(backend|reminders|bot)$/')
[[ " ${writers[*]} " == *' backend '* ]] || { echo 'Backend must be running before backup' >&2; exit 1; }
tmp=$(mktemp -d backups/.pending.XXXXXX)
resume() {
  "${compose[@]}" start "${writers[@]}" >/dev/null
}
trap resume EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"${compose[@]}" stop "${writers[@]}"
"${compose[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$tmp/database.dump"
"${compose[@]}" run --rm --no-deps -T --entrypoint tar backend czf - -C /app/uploads . > "$tmp/uploads.tar.gz"
"${compose[@]}" exec -T db pg_restore --list < "$tmp/database.dump" > /dev/null
tar tzf "$tmp/uploads.tar.gz" > /dev/null
archive="backups/$(date -u +%Y%m%dT%H%M%SZ)-${tmp##*.}.tar"
tar -cf "$tmp/backup.tar" -C "$tmp" database.dump uploads.tar.gz
mv "$tmp/backup.tar" "$archive"
rm -r "$tmp"
sha256sum "$archive" > "$archive.sha256"
echo "Backup created: $archive. Copy archive and checksum off the VPS."
