#!/usr/bin/env bash
# Run a command with GitHub SSH over port 443 (when corporate/firewall blocks TCP 22).
# Usage: ./scripts/with-github-ssh443.sh git push origin main
# See: https://docs.github.com/en/authentication/troubleshooting-ssh/using-ssh-over-the-https-port
set -euo pipefail
export GIT_SSH_COMMAND='ssh -o StrictHostKeyChecking=accept-new -o Hostname=ssh.github.com -p 443'
exec "$@"
