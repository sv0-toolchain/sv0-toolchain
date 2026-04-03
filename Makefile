# sv0-toolchain — aggregate build, test, and VM integration.
ROOT := $(abspath .)

.PHONY: help check build test test-mcp doc fmt integration-vm ci ci-all all

help:
	@echo "sv0-toolchain targets:"
	@echo "  make check           — compile sv0c + sv0vm (no unit tests)"
	@echo "  make build           — same as check"
	@echo "  make test            — unified harness (units, C+VM integration, bootstrap-in-sv0, doctests)"
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
