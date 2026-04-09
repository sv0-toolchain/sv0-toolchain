# sv0-toolchain — aggregate build, test, and VM integration.
ROOT := $(abspath .)

.PHONY: help check build test test-guards test-mcp doc fmt integration-vm ci ci-all all milestone-orient milestone-orient-show

help:
	@echo "sv0-toolchain targets:"
	@echo "  make check           — compile sv0c + sv0vm (no unit tests)"
	@echo "  make build           — same as check"
	@echo "  make test            — unified harness: sv0c units; Python guards (block comments, sv0doc,"
	@echo "                         task YAML, README sv0c gitlink); sv0vm; C+VM integration; bootstrap .sv0;"
	@echo "                         VM parity SML goldens; stage0 golden; doctests (see"
	@echo "                         task/sv0-toolchain-milestone-2-prep.Rmd)"
	@echo "  make test-guards     — Python-only: block comments, sv0doc baseline, task YAML, README SHA, vm-parity⊆bootstrap, milestone JSON + workspace table (no SML)"
	@echo "  make milestone-orient — ./scripts/sv0 milestone-orient list"
	@echo "  make milestone-orient-show ID=M3 — ./scripts/sv0 milestone-orient show <ID>"
	@echo "  make test-mcp        — sv0-mcp pytest (uv; skips if uv missing)"
	@echo "  make doc             — generate build/sv0-toolchain-doc + verify sv0doc paths"
	@echo "  make fmt             — .sv0 whitespace fmt + shell fmt (fmt-shell)"
	@echo "  make integration-vm  — VM integration only (also part of make test)"
	@echo "  make ci              — check + full test (no sv0-mcp)"
	@echo "  make ci-all          — ci, then sv0-mcp tests (uv + pytest when uv available)"
	@echo "  make all             — same as ci"

check build:
	@"$(ROOT)/scripts/sv0" check

test:
	@"$(ROOT)/scripts/sv0" test

test-guards:
	@"$(ROOT)/scripts/sv0" test-guards

milestone-orient:
	@"$(ROOT)/scripts/sv0" milestone-orient list

milestone-orient-show:
	@test -n "$(ID)" || (echo "usage: make milestone-orient-show ID=M3   (or ID=mcp-0, ID=M2-prep, …)" >&2; exit 1)
	@"$(ROOT)/scripts/sv0" milestone-orient show "$(ID)"

test-mcp:
	@"$(ROOT)/scripts/sv0" test-mcp

doc:
	@"$(ROOT)/scripts/sv0" doc

fmt:
	@"$(ROOT)/scripts/sv0" fmt

integration-vm:
	@"$(ROOT)/scripts/sv0" integration-vm

ci all: check test
	@echo "ci: OK"

ci-all: ci test-mcp
	@echo "ci-all: OK"
