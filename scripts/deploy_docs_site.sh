#!/usr/bin/env bash
set -euo pipefail

# This script is installed root-owned on the documentation server. The GitHub
# deploy key reaches it through a root-owned forced-command entrypoint.
if [[ ${EUID} -ne 0 ]]; then
  printf 'deploy script must run as root\n' >&2
  exit 77
fi
# Keep this check as defense in depth if a caller preserves the variable.
if [[ -n ${SSH_ORIGINAL_COMMAND:-} ]]; then
  printf 'deploy command arguments are not accepted\n' >&2
  exit 64
fi

readonly site_root=/opt/1panel/www/sites/docs.bearguin.cn
readonly backup_root=/opt/1panel/backup/website/docs.bearguin.cn/automatic
readonly max_archive_bytes=33554432
readonly max_extracted_bytes=67108864
readonly max_members=5000

umask 022
archive=$(mktemp /tmp/bearagent-docs-release.XXXXXX.tar.gz)
staging=

cleanup() {
  rm -f -- "$archive"
  if [[ -n "$staging" && -d "$staging" ]]; then
    rm -rf -- "$staging"
  fi
}
trap cleanup EXIT

# Read one byte past the limit so an oversized upload is detected before it can
# fill an unbounded temporary file.
head -c "$((max_archive_bytes + 1))" > "$archive"
archive_size=$(stat -c %s "$archive")
if ((archive_size == 0 || archive_size > max_archive_bytes)); then
  printf 'release archive is empty or exceeds the 32 MiB limit\n' >&2
  exit 65
fi

python3 - "$archive" "$max_extracted_bytes" "$max_members" <<'PY'
import pathlib
import sys
import tarfile

archive = pathlib.Path(sys.argv[1])
max_extracted = int(sys.argv[2])
max_members = int(sys.argv[3])
total = 0

with tarfile.open(archive, mode="r:gz") as bundle:
    members = bundle.getmembers()
    if not members or len(members) > max_members:
        raise SystemExit("release archive has an invalid member count")
    for member in members:
        name = member.name
        path = pathlib.PurePosixPath(name)
        if "\\" in name or path.is_absolute() or ".." in path.parts:
            raise SystemExit("release archive contains an unsafe path")
        if not (member.isfile() or member.isdir()):
            raise SystemExit("release archive contains a link or special file")
        total += member.size
        if total > max_extracted:
            raise SystemExit("release archive exceeds the 64 MiB extracted limit")
PY

release_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
staging="$site_root/index.release-$release_id"
backup="$backup_root/$release_id"
mkdir -p -- "$staging" "$backup"
tar --extract --gzip --file "$archive" --directory "$staging" \
  --no-same-owner --no-same-permissions

test -f "$staging/index.html"
test -f "$staging/zh-cn/index.html"
test -f "$staging/pagefind/pagefind-ui.js"
find "$staging" -type d -exec chmod 755 {} +
find "$staging" -type f -exec chmod 644 {} +
chown -R root:root "$staging"

mv -- "$site_root/index" "$backup/index-before"
mv -- "$staging" "$site_root/index"
staging=

if ! curl --fail --silent --show-error --location --max-time 20 \
  https://docs.bearguin.cn/zh-cn/ >/dev/null; then
  mv -- "$site_root/index" "$backup/index-failed"
  mv -- "$backup/index-before" "$site_root/index"
  printf 'public health check failed; previous release restored\n' >&2
  exit 69
fi

printf 'deployed docs release %s\n' "$release_id"
