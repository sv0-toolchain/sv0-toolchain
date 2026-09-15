#!/usr/bin/env bash
# shared shell utilities for sv0-toolchain agent scripts

sv0_log() {
    local level="$1"; shift
    echo "[$level] $*"
}

sv0_info() { sv0_log "INFO" "$@"; }
sv0_warn() { sv0_log "WARN" "$@"; }
sv0_fail() { sv0_log "FAIL" "$@"; exit 1; }
sv0_ok() { sv0_log "OK" "$@"; }

sv0_require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" &>/dev/null; then
        sv0_fail "$cmd not found in PATH"
    fi
}

sv0_require_file() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        sv0_fail "file not found: $file"
    fi
}

sv0_require_dir() {
    local dir="$1"
    if [[ ! -d "$dir" ]]; then
        sv0_fail "directory not found: $dir"
    fi
}

# Worker count for parallel per-file/per-case stages (self-host-sv0-loop,
# test-guards, ...). SV0_JOBS overrides; otherwise the host's online CPU
# count (getconf, then sysctl for macOS, then a fixed fallback).
sv0_jobs() {
    if [[ -n "${SV0_JOBS:-}" ]]; then
        printf '%s' "$SV0_JOBS"
        return 0
    fi
    local n
    n="$(getconf _NPROCESSORS_ONLN 2>/dev/null || true)"
    if [[ -z "$n" ]]; then
        n="$(sysctl -n hw.ncpu 2>/dev/null || true)"
    fi
    [[ -n "$n" && "$n" -ge 1 ]] || n=4
    printf '%s' "$n"
}
