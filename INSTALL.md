# Installing sv0

sv0 is distributed as **source** — there is no prebuilt binary package yet (planned
for a later release). You build the toolchain from this repository and use its
`sv0` driver to compile `.sv0` programs to native executables or bytecode.

This is the `v0.1.0` release. See [CHANGELOG.md](CHANGELOG.md) for what's included
and [README.md](README.md) for orientation.

## Prerequisites

- **git**, a POSIX shell, and a **C compiler** (`cc` / `clang` / `gcc`) — required
  to build the native compiler and to compile programs to executables.
- **Standard ML of New Jersey (SML/NJ)** — required for a cold build of the
  compiler (the SML reference bootstraps the first native binary) and to run the
  bytecode VM and the full test gate. The native sv0-built compiler is the default
  once bootstrapped.
- **Python 3.12+** — optional, for the developer guards (`./scripts/sv0 test-guards`).
- **z3** — optional, for `sv0 verify`; the verifier degrades gracefully to
  runtime-checked contracts when z3 is absent.

## Get the source

```bash
git clone --recurse-submodules git@github.com:sv0-toolchain/sv0-toolchain.git
cd sv0-toolchain
```

To pin this release exactly:

```bash
git checkout v0.1.0
git submodule update --init --recursive
```

## Build + smoke test

```bash
./scripts/sv0 check      # fast smoke: build the native compiler + load the VM
./scripts/sv0 test       # full gate (slower; needs SML): units, integration, parity, self-host
```

Run `./scripts/sv0` with no arguments for the full command list.

## Compile and run a program

```bash
# native executable (sv0 -> C -> host cc -> binary):
./scripts/sv0 native-compile sv0c/examples/learn/01_minimal_main.sv0

# or to bytecode, then run on the VM:
./scripts/sv0 vm-compile sv0c/examples/learn/01_minimal_main.sv0
./scripts/sv0 vm-run build/vm/01_minimal_main.sv0b

# inspect the generated C:
./scripts/sv0 emit-c examples/learn/01_minimal_main.sv0
```

Numbered tutorials live under [`sv0c/examples/learn/`](sv0c/examples/learn/).

## Next steps

- **Language spec:** [`sv0doc/`](sv0doc/README.md)
- **Developer workflow, git hooks, the task system:** [CONTRIBUTING.md](CONTRIBUTING.md)
- **Libraries built on sv0:** `sv0-mathlib` (numeric), `sv0-strings` (safe strings).
