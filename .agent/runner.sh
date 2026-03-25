#!/usr/bin/env bash
set -euo pipefail

AGENT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$AGENT_DIR/.." && pwd)"

usage() {
    echo "usage: .agent/runner.sh [options] <agent-file.Rmd>"
    echo ""
    echo "options:"
    echo "  --dry-run        show what would execute without running"
    echo "  --line N         run a specific directive by line number"
    echo "  --write-back     write output back into the document"
    echo "  --non-interactive use default values for /prompt: directives"
    echo "  -e KEY=VALUE     set environment variable"
    exit 1
}

DRY_RUN=false
WRITE_BACK=false
NON_INTERACTIVE=false
TARGET_LINE=""
AGENT_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --write-back) WRITE_BACK=true; shift ;;
        --non-interactive) NON_INTERACTIVE=true; shift ;;
        --line) TARGET_LINE="$2"; shift 2 ;;
        -e) export "${2}"; shift 2 ;;
        -*) echo "unknown option: $1"; usage ;;
        *) AGENT_FILE="$1"; shift ;;
    esac
done

[[ -z "$AGENT_FILE" ]] && usage
[[ ! -f "$AGENT_FILE" ]] && echo "error: file not found: $AGENT_FILE" && exit 1

AGENT_NAME="$(basename "$AGENT_FILE" .Rmd)"
AGENT_DIR_PATH="$(dirname "$AGENT_FILE")"
SCRIPT_DIR="$AGENT_DIR_PATH/$AGENT_NAME"

resolve_runner() {
    local ext="$1"
    local config="$AGENT_DIR/config.yaml"
    # simple yaml lookup for runner mapping
    local runner
    runner=$(grep -F "  $ext:" "$config" 2>/dev/null | awk '{print $2}')
    if [[ -n "$runner" ]]; then
        echo "$AGENT_DIR/runners/$runner"
    fi
}

run_script() {
    local script_path="$1"
    shift
    local ext=".${script_path##*.}"
    local runner
    runner=$(resolve_runner "$ext")

    if [[ -n "$runner" && -x "$runner" ]]; then
        "$runner" "$script_path" "$@"
    else
        echo "error: no runner configured for extension $ext" >&2
        return 1
    fi
}

check_require() {
    local dep="$1"
    local cmd
    cmd=$(echo "$dep" | awk '{print $1}')
    if ! command -v "$cmd" &>/dev/null; then
        echo "FAIL: $dep (not found in PATH)"
        return 1
    fi
    echo "OK: $dep"
    return 0
}

# phase 1: scan for /require: directives
REQUIRE_FAILED=false
while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^/require:\ (.+)$ ]]; then
        dep="${BASH_REMATCH[1]}"
        if ! check_require "$dep"; then
            REQUIRE_FAILED=true
        fi
    fi
done < "$AGENT_FILE"

if $REQUIRE_FAILED; then
    echo ""
    echo "error: unmet dependencies. workflow halted."
    exit 1
fi

# phase 2: sequential directive execution
ON_ERROR="halt"
LINE_NUM=0
LAST_RESULT=""

while IFS= read -r line || [[ -n "$line" ]]; do
    LINE_NUM=$((LINE_NUM + 1))

    if [[ "$line" =~ ^/env:\ (.+)$ ]]; then
        if $DRY_RUN; then
            echo "[dry-run] env: ${BASH_REMATCH[1]}"
        else
            eval export "${BASH_REMATCH[1]}"
        fi
        continue
    elif [[ "$line" =~ ^/on-error:\ (.+)$ ]]; then
        ON_ERROR="${BASH_REMATCH[1]}"
        continue
    fi

    [[ -n "$TARGET_LINE" && "$LINE_NUM" -ne "$TARGET_LINE" ]] && continue

    if [[ "$line" =~ ^/capture:\ (.+)$ ]]; then
        if $DRY_RUN; then
            echo "[dry-run] capture: ${BASH_REMATCH[1]} <- last result"
        else
            export "${BASH_REMATCH[1]}=$LAST_RESULT"
        fi

    elif [[ "$line" =~ ^/assert:\ (.+)$ ]]; then
        expr="${BASH_REMATCH[1]}"
        if $DRY_RUN; then
            echo "[dry-run] assert: $expr"
        else
            if ! eval "$expr"; then
                echo "ASSERT FAILED (line $LINE_NUM): $expr"
                exit 1
            fi
        fi

    elif [[ "$line" =~ ^/run:\ (.+)$ ]]; then
        cmd="${BASH_REMATCH[1]}"
        script_name=$(echo "$cmd" | awk '{print $1}')
        script_args=$(echo "$cmd" | cut -d' ' -f2- -s)
        script_path="$SCRIPT_DIR/$script_name"

        if $DRY_RUN; then
            echo "[dry-run] run: $script_path $script_args"
        else
            if [[ -f "$script_path" ]]; then
                LAST_RESULT="OK"
                eval "run_script \"$script_path\" $script_args" || {
                    rc=$?
                    LAST_RESULT="FAIL"
                    case "$ON_ERROR" in
                        halt) echo "HALTED at line $LINE_NUM (exit $rc)"; exit $rc ;;
                        continue) echo "WARN: failed at line $LINE_NUM (exit $rc), continuing" ;;
                        retry*) echo "TODO: retry not yet implemented"; exit $rc ;;
                        fallback*) echo "TODO: fallback not yet implemented"; exit $rc ;;
                    esac
                }
            else
                echo "error: script not found: $script_path"
                LAST_RESULT="FAIL"
                [[ "$ON_ERROR" == "halt" ]] && exit 1
            fi
        fi

    elif [[ "$line" =~ ^/include:\ (.+)$ ]]; then
        include_path="${BASH_REMATCH[1]}"
        if $DRY_RUN; then
            echo "[dry-run] include: $include_path"
        else
            if "$0" "$include_path"; then
                LAST_RESULT="OK"
            else
                rc=$?
                LAST_RESULT="FAIL"
                case "$ON_ERROR" in
                    halt) echo "HALTED at line $LINE_NUM: include $include_path failed (exit $rc)"; exit $rc ;;
                    continue) echo "WARN: include $include_path failed at line $LINE_NUM (exit $rc), continuing" ;;
                    retry*) echo "TODO: retry not yet implemented"; exit $rc ;;
                    fallback*) echo "TODO: fallback not yet implemented"; exit $rc ;;
                esac
            fi
        fi

    elif [[ "$line" =~ ^/ai:\ (.+)$ ]]; then
        if $DRY_RUN; then
            echo "[dry-run] ai: ${BASH_REMATCH[1]}"
        else
            echo "[skip] /ai: directives require Cursor or --ai flag"
        fi
    fi

done < "$AGENT_FILE"
