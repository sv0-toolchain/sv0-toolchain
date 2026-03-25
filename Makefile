# sv0-toolchain — aggregate build, test, and VM integration.
ROOT := $(abspath .)

.PHONY: help check build test test-mcp doc fmt integration-vm ci ci-all all

help:
	@echo "sv0-toolchain targets:"
	@echo "  make check           — compile sv0c + sv0vm (no unit tests)"
	@echo "  make build           — same as check"
	@echo "  make test            — sv0c suite + sv0vm bytecode tests"
	@echo "  make test-mcp        — sv0-mcp pytest (uv; skips if uv missing)"
	@echo "  make doc             — verify sv0doc + sv0-mcp doc paths"
	@echo "  make fmt             — bash syntax (+ shfmt if installed)"
	@echo "  make integration-vm  — compile sample .sv0 to .sv0b and run on sv0vm"
	@echo "  make ci              — SML-only: check + test + integration-vm (no sv0-mcp)"
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

ci all: check test integration-vm
	@echo "ci: OK"

ci-all: ci test-mcp
	@echo "ci-all: OK"
