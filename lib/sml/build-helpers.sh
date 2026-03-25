#!/usr/bin/env bash
# SML/NJ build helpers for sv0-toolchain agent scripts

sml_compile_cm() {
    local cm_file="$1"
    local project_root="$2"
    local full_path="$project_root/$cm_file"

    if [[ ! -f "$full_path" ]]; then
        echo "FAIL: CM file not found: $full_path"
        return 1
    fi

    echo "compiling $full_path..."
    local output rc
    output=$(cd "$project_root" && echo "CM.make \"$cm_file\";" | sml 2>&1)
    rc=$?

    echo "$output"
    if [[ $rc -eq 0 ]]; then
        echo "OK: $full_path compiled successfully"
    else
        echo "FAIL: $full_path compilation failed (exit $rc)"
    fi

    return $rc
}

sml_run_test() {
    local test_file="$1"
    local project_root="$2"
    local full_path="$project_root/$test_file"

    if [[ ! -f "$full_path" ]]; then
        echo "SKIP: test file not found: $full_path"
        return 0
    fi

    echo "running $full_path..."
    (cd "$project_root" && echo "use \"$test_file\";" | sml 2>&1)
    return $?
}

sml_export_heap() {
    local cm_file="$1"
    local heap_name="$2"
    local project_root="$3"
    local full_path="$project_root/$cm_file"

    if [[ ! -f "$full_path" ]]; then
        echo "FAIL: CM file not found: $full_path"
        return 1
    fi

    echo "exporting heap image: $heap_name from $full_path..."
    (cd "$project_root" && echo "CM.make \"$cm_file\"; SMLofNJ.exportFn(\"$heap_name\", Main.main);" | sml 2>&1)
    return $?
}
