#!/usr/bin/env bash
# Install SML/NJ for CI. Matches developer 110.99.x / 2026.x; apt smlnj is too old for sv0vm/sv0c.
# Linux x86-64 installs 110.99.9 from smlnj.org and falls back, when smlnj.org and its mirror
# are unreachable, to the NixOS-built SML/NJ from cache.nixos.org, pinned by store path. The
# other R1 hosts (Linux arm64, macOS arm64 and x86-64; CV-409) use that Nix build directly.
set -euo pipefail

SMLNJ_VERSION="${SMLNJ_VERSION:-110.99.9}"
ROOT="${SMLNJ_INSTALL_DIR:-$HOME/smlnj-${SMLNJ_VERSION}}"

# curl exit 28 = timeout; dist downloads can be slow. Used for config.tgz and inherited by install.sh child curls.
CURL_LONG=(curl -fsSL --connect-timeout 120 --max-time 1800 --retry 5 --retry-delay 20 --retry-all-errors)

append_path() {
  if [[ -d "$ROOT/bin" ]]; then
    export PATH="$ROOT/bin:$PATH"
    if [[ -n "${GITHUB_PATH:-}" ]]; then
      echo "$ROOT/bin" >>"$GITHUB_PATH"
    fi
  fi
}

write_fetch_config_for_installer() {
  # SML/NJ config/install.sh shells out to curl/wget; these defaults apply to child downloads.
  if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    cat >"$HOME/.curlrc" <<'EOF'
connect-timeout = 120
max-time = 1800
retry = 5
retry-delay = 20
retry-all-errors
EOF
    cat >"$HOME/.wgetrc" <<'EOF'
timeout = 120
tries = 5
waitretry = 20
EOF
  fi
}

download_config_tgz() {
  local dest="$1"
  local primary="https://smlnj.org/dist/working/${SMLNJ_VERSION}/config.tgz"
  local mirror="https://smlnj.cs.uchicago.edu/dist/working/${SMLNJ_VERSION}/config.tgz"
  if "${CURL_LONG[@]}" -o "$dest" "$primary"; then
    return 0
  fi
  echo "ci-install-smlnj: primary config.tgz failed, trying mirror..." >&2
  "${CURL_LONG[@]}" -o "$dest" "$mirror"
}

# Hydra builds of nixpkgs smlnj, signed by cache.nixos.org (x86_64-darwin's last is 110.99.9).
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) NIX_SMLNJ="/nix/store/w681j2v1xplprr505biwy6qwz0p8g1ra-smlnj-2026.3" ;;
  Linux-aarch64) NIX_SMLNJ="/nix/store/zr29j62f3v710d4166sj3ck2xg5m18vv-smlnj-2026.3" ;;
  Darwin-x86_64) NIX_SMLNJ="/nix/store/7vplah84i8wkndm7kllh3zwhqscz1czm-smlnj-110.99.9" ;;
  Darwin-arm64) NIX_SMLNJ="/nix/store/1milnnnw0n9g4l9dcy7qw1vmghrrc044-smlnj-2026.3" ;;
  *) echo "ci-install-smlnj: unsupported host $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac
NIX_INSTALLER="https://releases.nixos.org/nix/nix-2.28.4/install"

install_from_nix() {
  echo "ci-install-smlnj: installing ${NIX_SMLNJ#*-} from cache.nixos.org" >&2
  cd "$HOME"
  rm -rf "$ROOT" # a partial tree would be saved under the 110.99.9 cache key and block the real install
  if ! command -v nix-store >/dev/null; then
    if [[ "$(uname -s)" == Darwin ]]; then
      sh <("${CURL_LONG[@]}" "$NIX_INSTALLER") --daemon --yes # macOS supports only the multi-user install
    else
      sh <("${CURL_LONG[@]}" "$NIX_INSTALLER") --no-daemon --yes
    fi
  fi
  local profile
  for profile in "$HOME/.nix-profile/etc/profile.d/nix.sh" /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh; do
    if [[ -f "$profile" ]]; then
      set +u # the Nix profile scripts read unset variables
      # shellcheck disable=SC1090
      . "$profile"
      set -u
    fi
  done
  nix-store --realise "$NIX_SMLNJ" >/dev/null
  export PATH="$NIX_SMLNJ/bin:$PATH"
  if [[ -n "${GITHUB_PATH:-}" ]]; then
    echo "$NIX_SMLNJ/bin" >>"$GITHUB_PATH"
  fi
  sml '@SMLversion'
}

append_path
if [[ -x "$ROOT/bin/sml" ]]; then
  sml '@SMLversion'
  exit 0
fi

if [[ "$(uname -s)-$(uname -m)" != Linux-x86_64 ]]; then
  install_from_nix
  exit 0
fi

sudo apt-get update
sudo apt-get install -y build-essential curl wget

write_fetch_config_for_installer

mkdir -p "$ROOT"
cd "$ROOT"
rm -f config.tgz
if ! { download_config_tgz config.tgz && tar -xzf config.tgz && ./config/install.sh; }; then
  install_from_nix
  exit 0
fi

append_path
if [[ ! -x "$ROOT/bin/sml" ]]; then
  echo "ci-install-smlnj: sml not found under $ROOT/bin" >&2
  find "$ROOT" -maxdepth 4 -name sml -type f 2>/dev/null || true
  exit 1
fi
sml '@SMLversion'
