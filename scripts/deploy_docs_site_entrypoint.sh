#!/bin/sh
set -eu

# This root-owned entrypoint is the forced command in authorized_keys. Check the
# original SSH command before sudo clears it, then hand the archive on stdin to
# the privileged deployment script.
if [ -n "${SSH_ORIGINAL_COMMAND:-}" ]; then
  printf 'deploy command arguments are not accepted\n' >&2
  exit 64
fi

exec sudo -n /usr/local/sbin/deploy-bearagent-docs
