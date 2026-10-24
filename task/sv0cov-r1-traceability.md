---
title: "sv0cov R1 traceability (CV-417)"
---

# sv0cov R1 traceability (CV-417, 2026-10-24)

Every SPEC requirement whose phase is R1 (138) and every acceptance
criterion (135), mapped to the evidence that already meets it (done
checklist slices) and to the R1 slice that owns what remains. Generated from
the SPEC (`project-specs/sv0cov/SPEC.md`) and `task/sv0cov-checklist.Rmd`
citations, with the uncited items mapped by hand. Statuses:

- **met**: done slices carry the evidence;
- **partly met**: done slices meet part of it, the owner completes it;
- **owned**: an open R1 slice owns all of it;
- **conditional**: applies only on the dedicated-host path (CV-315 plan);
- **post-R1**: owned by a post-R1 slice;
- **mismatch**: the SPEC and the implementation or an accepted decision
  disagree; listed for an owner amendment (below).

No item is unmapped. R1 still re-verifies every "met" item at the gate review
(CV-415) against the final revision.

## Summary

- **requirements:** 2 conditional, 35 met, 3 mismatch, 66 owned, 32 partly met
- **acceptance criteria:** 1 conditional, 89 met, 2 mismatch, 27 owned, 15 partly met, 1 post-R1

## SPEC mismatches for owner amendment

- **M1.** COV-REP-017 says the report has twenty-two top-level members; it has 24 since CV-312 (`changes`) and CV-313 (`ratchet`).
- **M2.** COV-SCP-009 names Python *and sv0* scope matchers; the sv0 implementation is post-R1 (CV-902). Through R1 only the Python matcher can exist.
- **M3.** COV-MET-007 asks for proof provenance on proven-impossible outcomes; no schema has a provenance field (the `statically_unreachable` status is all a record carries). Amend, or add a field before the CV-412 freeze.
- **M4.** AC-073 says only dedicated-host evidence can pass R1 performance; DEC-087 (§24.1) admits `managed-ci-recorded` campaigns with exception records, the path chosen in CV-315.
- **M5.** AC-133 requires a distinct human approver; DEC-087 admits single-maintainer approval under compensating controls (COV-PKG-025).
- **M6.** §20.1 lists seven commands and §20.1.1 exactly seven root subcommands; `sv0cov baseline` (CV-313) exists unadvertised (CV-421).
- **M7.** §20.1 lets `check` take a native report; §16.5 says the indexed profile is the only `check` input. D-10 chose native reports in R1 (CV-416).
- **M8.** §21.5 requires a reserved root-package spelling for sources without a package but does not give it; CV-402 uses `(root)` (owner decision).

## Requirements (phase R1)

| requirement | text | status | evidence | owner | note |
|---|---|---|---|---|---|
| COV-GOV-007 | Release claims SHALL link reproducible evidence at exact revisions. | partly met | CV-417 | CV-415 |  |
| COV-GOV-008 | Stable format and requirement identifiers SHALL never be silently reused. | partly met | CV-009 (append-only registry), CV-417 (IDs kept at the R1 re-slice) | CV-412 | format identifiers at the freeze |
| COV-MAP-010 | Available report source SHALL match its compiled digest by default. | met | CV-229, CV-231 |  | COV1004 unless `--allow-source-mismatch` |
| COV-MAP-011 | Absolute host paths SHALL be omitted from public artifacts by default. | owned |  | CV-424 |  |
| COV-MAP-012 | Canonical maps SHALL be byte-identical for equivalent clean builds. | met | CV-111 |  |  |
| COV-MET-005 | Short-circuit evaluated and skipped outcomes SHALL be represented. | met | CV-307 |  |  |
| COV-MET-006 | A no-`else` `if` SHALL retain an implicit false outcome. | met | CV-109 |  |  |
| COV-MET-007 | Proven impossible outcomes SHALL be visible and excluded with proof provenance. | mismatch | CV-201, CV-203 | owner | M3 |
| COV-MET-011 | Zero denominators SHALL display `N/A` and serialize a null ratio. | met | CV-230 |  |  |
| COV-MET-012 | Policy decisions SHALL use integer numerator/denominator arithmetic. | met | CV-229, CV-231 |  |  |
| COV-MET-013 | Condition coverage and MC/DC SHALL not be claimed by R1 outputs. | met | CV-228 (closed schemas: five metrics only) |  | by construction |
| COV-MET-014 | Metric classification SHALL be backend-independent. | owned |  | CV-407 |  |
| COV-MET-017 | Derived region counts SHALL use per-context interval lower bounds, retain inexact zero, aggregate those con... | partly met | CV-204, CV-221 | CV-404 |  |
| COV-INS-006 | Generated-C counter collection SHALL use shared C11 atomic `u64` storage and relaxed saturating compare-and... | partly met | CV-210 | CV-422 |  |
| COV-INS-007 | Normal exit and defined contract failure SHALL flush a complete profile. | partly met | CV-115 | CV-423 |  |
| COV-INS-008 | Interrupted/incomplete runs SHALL not be reported as zero coverage. | partly met | CV-234 | CV-423 |  |
| COV-INS-009 | Overflow flags SHALL be updated atomically and SHALL identify every saturated counter. | partly met | CV-210 | CV-422 |  |
| COV-INS-010 | Implementations SHALL NOT assume `u64` atomics are lock-free without a recorded host probe. | partly met | CV-210 | CV-422 |  |
| COV-INS-011 | VMs with serialized execution MAY use non-atomic internal storage only when externally observable saturatio... | partly met | CV-207, CV-171 (VM counts and saturation equal C) | CV-407 |  |
| COV-INS-012 | Complete orderly multithreaded profiles SHALL require coverage-producing threads to be quiescent before fin... | partly met | CV-210 | CV-422 |  |
| COV-INS-013 | Saturated values SHALL be represented as lower bounds with explicit saturation metadata. | owned |  | CV-404 |  |
| COV-INS-016 | Only independently entered process images and toolchain-managed spawn-and-exec descendants SHALL be eligibl... | owned |  | CV-405 |  |
| COV-C-004 | Multiple instrumented modules SHALL register without counter collision. | partly met | CV-206 | CV-423 |  |
| COV-C-007 | The native runtime SHALL prevent a fork child from publishing inherited counters, retain an unresolved pare... | owned |  | CV-405 |  |
| COV-VM-005 | v1 VM, v2 VM, and generated-C indexed counts SHALL match for deterministic conformance fixtures. | owned |  | CV-407 |  |
| COV-VM-012 | Coverage-capable `sv0vm-v2-typed` SHALL carry equivalent coverage metadata inline. | owned |  | CV-462 |  |
| COV-VM-013 | After physical-integrity validation, the v1 companion and v2 inline metadata SHALL resolve to the same cano... | partly met | CV-026 | CV-463 |  |
| COV-VM-014 | Both required VM coverage profiles SHALL pass the full semantic, security, portability, and performance con... | owned |  | CV-407 |  |
| COV-VM-019 | The v2 coverage section SHALL use the unique ASCII tag `COVR` (`43 4f 56 52`). | partly met | CV-102 | CV-461 |  |
| COV-VM-022 | v2 `bytecode_sha256` SHALL hash the complete canonical `.sv0b` with exactly its own 32-byte field zero-fill... | owned |  | CV-462, CV-463 |  |
| COV-VM-023 | The v2 `COVR` 1.0 payload SHALL use the exact packed little-endian layout, constants, ASCII bounds, final d... | partly met | CV-026 | CV-461 |  |
| COV-VM-026 | VM host-process operations SHALL expose the same fresh-image and managed spawn-and-exec coverage boundary a... | owned |  | CV-405 |  |
| COV-FMT-012 | The R1 runtime SHALL perform neither periodic profile checkpoints nor memory-mapped continuous counter writes. | owned |  | CV-406 |  |
| COV-FMT-024 | Diagnostic provenance and release evidence SHALL record the resolved tier and numeric ceilings. | partly met | CV-224, CV-228 (resolved tier in the report) | CV-415 | release evidence |
| COV-FMT-037 | `sv0cov.export-manifest` version `1.0` SHALL use the exact closed fourteen-property canonical JSON schema,... | owned |  | CV-403 |  |
| COV-MRG-006 | Source-version conflicts SHALL block passing policy. | met | CV-223 |  |  |
| COV-MRG-007 | Rejected inputs SHALL remain in the result inventory. | met | CV-223 |  |  |
| COV-CTX-004 | Context filtering SHALL not mutate aggregate counts. | met | CV-308 |  |  |
| COV-SCP-004 | Dependency ownership SHALL derive from build metadata, not path spelling. | met | CV-209, CV-417 (B12: dependency units no longer reach the project) |  |  |
| COV-SCP-009 | Python and sv0 scope matchers SHALL reproduce the frozen checksum-pinned Git 2.55.0 `check-ignore --no-inde... | mismatch | CV-030, CV-310 (Python matcher) | owner | M2 |
| COV-EXC-005 | Exclusions SHALL remain visible in native, HTML, and terminal summaries. | met | CV-314 |  |  |
| COV-EXC-006 | An exclusion SHALL apply identically to both backends. | partly met | CV-305 (C and VM v1) | CV-407 | v2 |
| COV-EXC-011 | `coverage` exclusions SHALL produce identical plans for generated C and both VM profiles. | partly met | CV-305 (C and VM v1) | CV-407 | v2 |
| COV-EXC-015 | Expression-position `coverage` attributes SHALL be rejected with a targeted diagnostic. | met | CV-302 |  |  |
| COV-EXC-017 | Formatting SHALL preserve attribute attachment and produce canonical item/statement layout. | met | CV-303 |  |  |
| COV-EXC-018 | Comment directives SHALL remain the R1 mechanism for expression-level exclusions. | met | CV-304, CV-305 |  |  |
| COV-EXC-023 | Independent line-only exclusion and arbitrary metric lists SHALL be unsupported. | met | CV-305 |  |  |
| COV-EXC-025 | Reports SHALL retain excluded subtree and contract evaluation evidence with owning reasons. | met | CV-314 |  |  |
| COV-CLI-005 | Diagnostics SHALL have stable codes and JSON representation. | met | CV-009, CV-225 |  |  |
| COV-CLI-009 | Every command SHALL support exact `human` and `json-lines` diagnostic formats; JSON Lines SHALL contain onl... | met | CV-009, CV-225 |  |  |
| COV-CLI-010 | `version --json` SHALL emit only the exact closed fourteen-property self-hashed `sv0cov.version` 1.0 capabi... | partly met | CV-021, CV-316 (pre-R1 subsets) | CV-415 | exact R1 inventories at 1.0.0 |
| COV-CLI-011 | `doctor` SHALL use standalone mode by default and toolchain mode only with one explicit `--toolchain-root`;... | met | CV-235, CV-242 |  |  |
| COV-CLI-012 | The root driver SHALL expose only `./scripts/sv0 coverage <run\\|merge\\|report\\|check\\|clean\\|doctor\\|... | partly met | CV-241 | CV-421, CV-430 | M6 |
| COV-CLI-013 | Root coverage dispatch SHALL invoke only exact tracked mode-`100755` path `sv0cov/scripts/sv0cov` beneath t... | partly met | CV-241 | CV-430 |  |
| COV-CFG-007 | Native reports SHALL encode effective configuration as exact closed `sv0cov.resolved-configuration` 1.0 usi... | met | CV-228 |  |  |
| COV-REP-004 | LCOV SHALL export functions, lines, branches, and an information-loss manifest. | partly met | CV-401 (functions, lines, branches) | CV-403 | information-loss manifest |
| COV-REP-005 | Cobertura SHALL validate and document lossy mappings. | partly met | CV-402 (pinned-DTD validation; docs/cobertura.md) | CV-403 | loss manifest |
| COV-REP-006 | Every report format SHALL be byte-identical across repeated renders of the exact same indexed input under S... | owned |  | CV-424 |  |
| COV-REP-007 | HTML fixture reports SHALL meet WCAG 2.2 AA release checks. | partly met | CV-309 | CV-408 |  |
| COV-REP-008 | LCOV export SHALL implement only `sv0cov-lcov-r1-core` and its exact Section 21.4 record inventory. | met | CV-401 |  |  |
| COV-REP-009 | The LCOV core profile SHALL be accepted by checksum-pinned LCOV 1.16 and 2.5 `lcov` and `genhtml` consumers... | owned |  | CV-418 |  |
| COV-REP-010 | LCOV and Cobertura line hits SHALL use the specified binary projection in which partial is not covered. | met | CV-401 (LCOV), CV-402 (Cobertura) |  |  |
| COV-REP-011 | Cobertura export SHALL implement only `sv0cov-cobertura-r1-core` and validate offline against the exact pin... | met | CV-402 (vendored digest-pinned DTD, offline stdlib validator) |  |  |
| COV-REP-012 | Cobertura output SHALL omit `DOCTYPE`, external entities, processing instructions, extensions, and absolute... | met | CV-402 (writer never emits them; reader refuses them) |  |  |
| COV-REP-013 | A GitLab coverage-visualization smoke fixture SHALL resolve normalized logical paths and preserve the decla... | owned |  | CV-419 |  |
| COV-REP-014 | Every standard export SHALL have associated native JSON and an exact `sv0cov.export-manifest` 1.0 commit re... | owned |  | CV-403 |  |
| COV-REP-017 | `sv0cov.report` version `1.0` SHALL use the exact closed twenty-two-property top-level schema and every nes... | mismatch | CV-228, CV-312, CV-313 | owner | M1 |
| COV-REP-018 | Native-report summaries, contexts, inputs, exclusions, policy, saturation, provenance, configuration, compl... | met | CV-229 |  |  |
| COV-REP-019 | Every native contract record SHALL preserve its exact nullable nearest-function reference, and every entity... | met | CV-229 |  |  |
| COV-REP-020 | Count records and the saturation inventory SHALL distinguish exact zero from an inexact zero lower bound an... | met | CV-229 |  |  |
| COV-REP-021 | Native report detail SHALL preserve compiler and target map identity, point identity discriminators and out... | met | CV-229 |  |  |
| COV-POL-006 | Incomplete, stale, incompatible, or rejected evidence SHALL block a passing check. | met | CV-231 |  |  |
| COV-POL-007 | Saturation policy SHALL default to `fail` and MAY be set only explicitly to `allow-ordinary`. | owned |  | CV-404 |  |
| COV-POL-008 | `allow-ordinary` SHALL authorize only function, region, line, and branch zero/nonzero checks. | owned |  | CV-404 |  |
| COV-POL-009 | Contract outcome counts, exact context counts, exact-count assertions, and incompatible ratchets SHALL fail... | owned |  | CV-404 |  |
| COV-POL-010 | Saturation policy SHALL be recorded in resolved configuration, native reports, baselines, and evidence mani... | owned |  | CV-404 |  |
| COV-POL-011 | Standard exports with saturation SHALL fail unless diagnostic-only lossy export is explicit and manifested. | owned |  | CV-420 |  |
| COV-POL-015 | Reports SHALL record supplied base spelling, resolved reference commit, current `HEAD`, and merge-base commit. | met | CV-311, CV-312 |  |  |
| COV-POL-019 | Dirty changed-region evidence SHALL record `HEAD`, relevant path states, source digests, the canonical diff... | met | CV-311, CV-312 |  |  |
| COV-POL-021 | A dirty result SHALL NOT be represented as reproducible from `HEAD` alone. | met | CV-312 |  | `clean`; terminal/HTML say dirty is not reproducible from HEAD |
| COV-POL-024 | Native, terminal, and HTML reports SHALL preserve every policy assertion's selector identity, membership, e... | met | CV-229, CV-230, CV-309, CV-310 |  |  |
| COV-POL-025 | Exclusion caps SHALL compare each metric's excluded units with its pre-exclusion total exactly, while recor... | met | CV-314 |  |  |
| COV-POL-027 | `allow-ordinary` SHALL use only proven-positive lower bounds for coverage and SHALL permit conservative fai... | owned |  | CV-404 |  |
| COV-SEC-005 | Public artifacts SHALL omit host/user/process metadata by default. | owned |  | CV-424 |  |
| COV-SEC-008 | Doctor SHALL use one private bounded temporary directory, fixed child and aggregate time/output/storage lim... | owned |  | CV-425 |  |
| COV-PORT-001 | macOS arm64, macOS x86-64, Linux arm64, and Linux x86-64 SHALL all be required host combinations. | owned |  | CV-409 |  |
| COV-PORT-002 | Each required host SHALL execute both generated-C and sv0vm coverage workflows. | owned |  | CV-409 |  |
| COV-PORT-003 | Canonical coverage meaning and canonical semantic-projection bytes SHALL be platform-independent. | owned |  | CV-409 |  |
| COV-PORT-004 | Windows SHALL remain explicitly unsupported rather than inferred from compatibility layers. | owned |  | CV-409 |  |
| COV-PORT-005 | The Python implementation SHALL support CPython 3.13 and 3.14 on every required host combination. | partly met | CV-006 | CV-409 |  |
| COV-PORT-006 | Unsupported Python versions SHALL fail early with an actionable version diagnostic. | partly met | CV-031 | CV-409 |  |
| COV-PORT-007 | Repository-local Python launchers SHALL resolve exact basename `python3.14` then `python3.13` by Section 20... | partly met | CV-031 | CV-409 |  |
| COV-PERF-002 | Section 24 budgets SHALL pass on all four required host combinations. | owned |  | CV-428 |  |
| COV-PERF-003 | Each required OS/architecture combination SHALL be an independent performance reference-host class. | owned |  | CV-428 |  |
| COV-PERF-004 | Measurements from different host classes SHALL NOT be pooled or used to compensate for another host's failure. | owned |  | CV-428 |  |
| COV-PERF-006 | Timed execution SHALL run directly on the named architecture; virtual hosts SHALL meet the pinned non-overc... | owned |  | CV-428 |  |
| COV-PERF-008 | Benchmark categories SHALL have equal aggregate weight, and geometric means SHALL be limited to dimensionle... | owned |  | CV-410 |  |
| COV-PERF-009 | Every fixture, category, and host result SHALL remain visible; aggregate success SHALL NOT hide a per-fixtu... | owned |  | CV-410 |  |
| COV-PERF-010 | CPython 3.13 and 3.14 SHALL retain four-host functional conformance even when only the qualified host descr... | owned |  | CV-428 |  |
| COV-PERF-013 | Required real-project fixtures SHALL be content-addressed and runnable without network access. | partly met | CV-036 | CV-427 |  |
| COV-PERF-015 | Every timed run SHALL validate its expected semantic result before contributing performance evidence. | owned |  | CV-427 |  |
| COV-PERF-016 | Native contention evidence SHALL include one, two, four, and eight threads with shared and disjoint counters. | owned |  | CV-427 |  |
| COV-PERF-017 | VM dispatch evidence SHALL cover equivalent v1 and v2 programs and identify profile-local overhead. | owned |  | CV-427 |  |
| COV-PERF-018 | Scale evidence SHALL exercise 250,000 report points and 1,000,000 point/profile pairs. | owned |  | CV-427 |  |
| COV-PERF-020 | A corpus revision SHALL version, justify, overlap-measure, and fully rebaseline every host class. | owned |  | CV-427 |  |
| COV-PERF-023 | Dedicated or demonstrably non-overcommitted reference hosts meeting Section 24.1 floors, or a `managed-ci-r... | owned |  | CV-410 |  |
| COV-PERF-024 | Managed CI performance results SHALL NOT satisfy an R1 performance gate except as a `managed-ci-recorded` c... | owned |  | CV-410 |  |
| COV-PERF-025 | A transition to dedicated hosts SHALL include three complete overlap campaigns per host class without conve... | conditional | CV-315 plan | CV-428 | only if a dedicated host appears |
| COV-PERF-026 | Dedicated-host replacement SHALL use the same descriptor, overlap, and complete four-host rebaseline proced... | conditional | CV-315 plan | CV-428 | only if a dedicated host appears |
| COV-PERF-027 | Instrumented compile p95 overhead SHALL be at most 20% for every applicable dedicated-host corpus result. | owned |  | CV-428 |  |
| COV-PERF-028 | Generated artifact geometric-mean growth SHALL be at most 30%, and a fixture above 75% SHALL require a prio... | owned |  | CV-428 |  |
| COV-PERF-029 | Region-plus-branch execution p95 overhead SHALL be at most 20% for every applicable dedicated-host corpus r... | owned |  | CV-428 |  |
| COV-PERF-030 | Runtime counter memory SHALL be at most 16 bytes per planned point plus 8 MiB fixed process overhead. | owned |  | CV-428 |  |
| COV-PERF-031 | Merging 1,000,000 point/profile pairs SHALL take at most 10 seconds and 1 GiB RSS. | owned |  | CV-428 |  |
| COV-PERF-032 | Native and terminal reporting of 250,000 points SHALL take at most 5 seconds and 768 MiB RSS. | owned |  | CV-428 |  |
| COV-PERF-033 | HTML reporting of 250,000 points SHALL take at most 20 seconds and 1 GiB RSS. | owned |  | CV-428 |  |
| COV-PERF-034 | Five clean deterministic executions SHALL have identical canonical maps and semantic projections, and five... | owned |  | CV-428 |  |
| COV-PERF-035 | A missed performance target SHALL block release unless an evidence-backed specification change is accepted... | owned |  | CV-410, CV-428 |  |
| COV-PERF-036 | Correctness or integrity SHALL NOT be weakened to meet a performance target. | owned |  | CV-410 |  |
| COV-REL-002 | Both backends SHALL pass identical semantic conformance fixtures. | owned |  | CV-407 |  |
| COV-REL-003 | Every required gate SHALL be supported by immutable evidence. | owned |  | CV-415 | evidence manifest |
| COV-REL-004 | Installation and removal SHALL pass on every required OS/architecture combination. | owned |  | CV-426 |  |
| COV-RW-001 | Public formats and CLI semantics SHALL be implementation-language-neutral. | partly met | CV-011 (language-neutral schemas) | CV-412 | cross-reader parity at the freeze |
| COV-LIC-008 | Every third-party component SHALL record source, version/revision, digest, concluded license, obligations,... | owned |  | CV-411 |  |
| COV-LIC-009 | Missing, ambiguous, incompatible, or unfulfilled third-party licensing SHALL block distribution of the affe... | owned |  | CV-411 |  |
| COV-LIC-010 | Release artifacts SHALL include reconciled SPDX SBOM, license inventory, required notices, checksums, and p... | owned |  | CV-411 |  |
| COV-PKG-002 | GitHub Releases SHALL include reproducible sdist, universal wheel, toolchain source archive, checksums, SBO... | owned |  | CV-413 |  |
| COV-PKG-003 | Unique assets SHALL be built once from a signed immutable tag and promoted byte-for-byte without rebuild. | owned |  | CV-413 |  |
| COV-PKG-004 | An existing release version or filename SHALL NOT be replaced with different bytes. | owned |  | CV-413 |  |
| COV-PKG-005 | The wheel SHALL be `py3-none-any` and contain every required Python, schema, report-asset, project-owned do... | owned |  | CV-426 |  |
| COV-PKG-006 | A native Python extension or precompiled runtime SHALL require a packaging amendment and platform-wheel mat... | owned |  | CV-426 |  |
| COV-PKG-008 | Installation from a locally verified wheel and uninstall SHALL pass on all eight required host/interpreter... | owned |  | CV-426 |  |
| COV-PKG-009 | The root submodule SHALL pin a full commit governed by exact `compatibility/sv0cov.json` and pass clean rec... | partly met | CV-240 | CV-430 |  |
| COV-PKG-010 | Build, test, and execution SHALL perform no implicit package or release download. | owned |  | CV-426 |  |
| COV-PKG-011 | GitHub publication and toolchain pinning SHALL follow a tested ordered release and rollback procedure. | owned |  | CV-414 |  |
| COV-PKG-013 | The root toolchain SHALL validate `sv0cov.version` 1.0 through the exact Section 20.1.1 namespace and compa... | partly met | CV-241 | CV-430 |  |
| COV-PKG-014 | `sv0-toolchain` SHALL commit the exact canonical compatibility policy with the matching gitlink, validate a... | partly met | CV-240 | CV-430 |  |
| COV-PKG-016 | Every R1 Python production path SHALL use only the qualified CPython standard library and project-owned `sv... | partly met | CV-004, CV-033 | CV-426 |  |

## Acceptance criteria

| criterion | text | status | evidence | owner | note |
|---|---|---|---|---|---|
| AC-001 | generated-C/VM identity | met | CV-027, CV-171 |  |  |
| AC-002 | generated-C/VM counts | met | CV-171 |  |  |
| AC-003 | default scope ignores directory conventions | met | CV-209, CV-417 (B12 fixed; `tests/test_default_scope.py`) |  |  |
| AC-004 | generated implementation is not charged | met | CV-113, CV-205 (maps name only sv0 sources) |  | by construction |
| AC-005 | stale source fails closed | met | CV-229, CV-231 |  |  |
| AC-006 | malformed exclusion | met | CV-305 |  |  |
| AC-007 | backend-neutral exclusion | met | CV-305 |  |  |
| AC-008 | partial line | met | CV-202, CV-230 |  |  |
| AC-009 | implicit false branch | met | CV-109 |  |  |
| AC-010 | contract separation | met | CV-306 |  |  |
| AC-011 | parallel determinism | met | CV-223 |  |  |
| AC-012 | corrupt raw profile | met | CV-223, CV-227 |  |  |
| AC-013 | duplicate artifact | met | CV-223, CV-227 |  |  |
| AC-014 | exact threshold | met | CV-231 |  |  |
| AC-015 | empty explicit scope | met | CV-231 |  |  |
| AC-016 | changed regions | met | CV-312 |  |  |
| AC-017 | ratchet exclusion growth | met | CV-313 |  |  |
| AC-018 | direct command execution | met | CV-233 |  |  |
| AC-019 | inaccessible VM capability | met | CV-122 |  |  |
| AC-020 | offline HTML | partly met | CV-309 | CV-408 |  |
| AC-021 | hostile source text | met | CV-309 |  |  |
| AC-022 | test command failure | met | CV-234 |  |  |
| AC-023 | zero-overhead off mode | met | CV-111 |  |  |
| AC-024 | context aggregation | met | CV-308 |  |  |
| AC-025 | reproducible report | met | CV-309 |  |  |
| AC-026 | coverage opcode is stack-neutral | met | CV-119 |  |  |
| AC-027 | v1 binding is explicit and digest-bound | met | CV-120 |  |  |
| AC-028 | v1 and v2 binding equivalence | partly met | CV-026 | CV-463 |  |
| AC-029 | exact coverage instruction encoding | met | CV-117, CV-119 |  |  |
| AC-030 | exact VM coverage identifiers | met | CV-102 |  |  |
| AC-031 | canonical sparse raw profile | met | CV-024 |  |  |
| AC-032 | hard termination remains incomplete in R1 | owned |  | CV-406 |  |
| AC-033 | post-R1 continuous data remains qualified | post-R1 |  | CV-904 |  |
| AC-034 | CRC32C transport integrity | met | CV-023 |  |  |
| AC-035 | contended atomic hit counting | met | CV-210 |  |  |
| AC-036 | atomic saturation | met | CV-210 |  |  |
| AC-037 | saturation fails by default | owned |  | CV-404 |  |
| AC-038 | explicit ordinary-metric saturation override | owned |  | CV-404 |  |
| AC-039 | exact native coverage namespace | met | CV-113 |  |  |
| AC-040 | statement attribute attachment | met | CV-305 |  |  |
| AC-041 | expression attribute is rejected | met | CV-305 |  |  |
| AC-042 | branch-only exclusion remains narrow | met | CV-305, CV-307 |  |  |
| AC-043 | contract exclusion does not disable enforcement | met | CV-305, CV-306 |  |  |
| AC-044 | redundant nested exclusion fails | met | CV-305 |  |  |
| AC-045 | changed coverage requires an explicit base | met | CV-311, CV-312 |  |  |
| AC-046 | ambiguous merge base fails | met | CV-311, CV-312 |  |  |
| AC-047 | tracked dirty source participates | met | CV-311, CV-312 |  |  |
| AC-048 | compiled untracked source blocks changed coverage | met | CV-311, CV-312 |  |  |
| AC-049 | source mutation makes the run stale | met | CV-311, CV-312 |  |  |
| AC-050 | LCOV core works across the pinned consumer range | owned |  | CV-418 |  |
| AC-051 | Cobertura core is deterministic and offline-safe | partly met | CV-402 (determinism, timestamp 0, offline DTD, no DOCTYPE/PI/extension/host path) | CV-419 | GitLab smoke |
| AC-052 | standard export loss is explicit | owned |  | CV-403 |  |
| AC-053 | extended export profiles remain unavailable through R1 | partly met | CV-401, CV-402 (core profiles only) | CV-403 | profile selection at the CLI |
| AC-054 | standard raw-profile limits apply by default | met | CV-025 |  |  |
| AC-055 | the large tier is explicit | met | CV-211, CV-224 |  |  |
| AC-056 | custom limits require both ceilings | met | CV-211 |  |  |
| AC-057 | encoded lengths cannot authorize allocation | met | CV-025 |  |  |
| AC-058 | context presence is byte-exact | met | CV-308 |  |  |
| AC-059 | exactly one backend is identified | met | CV-024, CV-025 |  |  |
| AC-060 | overflow metadata is internally consistent | met | CV-024, CV-025, CV-115 |  |  |
| AC-061 | completion marker rejects partial and byte-swapped files | met | CV-025 |  |  |
| AC-062 | one host failure cannot be averaged away | owned |  | CV-410 |  |
| AC-063 | reference-host evidence is reproducible and native | owned |  | CV-428 |  |
| AC-064 | benchmark rules cannot move after results | partly met | CV-035 (frozen protocol) | CV-410 |  |
| AC-065 | aggregate reporting preserves local failures | owned |  | CV-410 |  |
| AC-066 | hybrid corpus is complete and replayable | partly met | CV-036 | CV-427 |  |
| AC-067 | incorrect work cannot win a benchmark | owned |  | CV-410, CV-427 |  |
| AC-068 | native contention measures distinct costs | owned |  | CV-427 |  |
| AC-069 | corpus changes require complete rebaseline | owned |  | CV-427 |  |
| AC-070 | managed CI evidence is explicitly provisional | met | CV-037 |  |  |
| AC-071 | managed runner drift splits the trend | met | CV-037, CV-315 |  |  |
| AC-072 | dedicated-host transition requires overlap | conditional | CV-315 plan | CV-428 | only if a dedicated host appears |
| AC-073 | only dedicated evidence can pass R1 performance | mismatch |  | owner | M4 |
| AC-074 | repository license classes are machine-verifiable | partly met | CV-001, CV-034 | CV-411 |  |
| AC-075 | ordinary output is not relicensed | partly met | CV-001, CV-034 | CV-411 |  |
| AC-076 | copied project bytes retain notices | owned |  | CV-411 |  |
| AC-077 | unresolved third-party licensing fails closed | owned |  | CV-411 |  |
| AC-078 | release assets are built once | partly met | CV-243 (dry run) | CV-413 |  |
| AC-079 | wheel is portable and complete | partly met | CV-243 | CV-426 |  |
| AC-080 | registry installation is not implied | partly met | CV-005, CV-243 | CV-413 |  |
| AC-081 | toolchain pin cannot precede a usable release | owned |  | CV-414 |  |
| AC-082 | published bytes are immutable by version | owned |  | CV-413 |  |
| AC-083 | compile and execution overhead boundaries are exact | owned |  | CV-428 |  |
| AC-084 | aggregate size cannot hide an extreme fixture | owned |  | CV-428 |  |
| AC-085 | memory budget follows the point formula | owned |  | CV-428 |  |
| AC-086 | scale operations meet both time and memory limits | owned |  | CV-428 |  |
| AC-087 | deterministic artifacts have zero tolerance | partly met | CV-111, CV-223 | CV-428 |  |
| AC-088 | optimization cannot trade away correctness | owned |  | CV-428 |  |
| AC-089 | profile identity distinguishes equal executions from copies | met | CV-223 |  |  |
| AC-090 | raw format version is exact and fail-closed | met | CV-025 |  |  |
| AC-091 | modules share one program map and counter arena | met | CV-016, CV-205 |  |  |
| AC-092 | v2 metadata is bound to the complete bytecode | owned |  | CV-463 |  |
| AC-093 | COVR 1.0 has one exact binary representation | met | CV-024, CV-026 |  |  |
| AC-094 | v1 binding 1.0 is closed and canonical | met | CV-026 |  |  |
| AC-095 | zero-counter instrumentation proves orderly execution | met | CV-207 |  |  |
| AC-096 | process creation never duplicates inherited coverage | owned |  | CV-405 |  |
| AC-097 | cross-run aggregation requires an exact declared set | met | CV-223 |  |  |
| AC-098 | ambient environment cannot change coverage policy | met | CV-224, CV-237 |  |  |
| AC-099 | overlapping scopes are cumulative assertions | met | CV-310 |  |  |
| AC-100 | scope patterns are Gitignore-compatible and isolated | met | CV-030 |  |  |
| AC-101 | coverage configuration schema 1.0 is closed | met | CV-029 |  |  |
| AC-102 | threshold syntax and CLI mapping are exact | met | CV-029 |  |  |
| AC-103 | report selection and output publication are unambiguous | met | CV-309 |  |  |
| AC-104 | export commit manifests bind complete standard-export evidence | owned |  | CV-403 |  |
| AC-105 | native JSON report 1.0 is closed and self-consistent | met | CV-229 |  |  |
| AC-106 | contract coverage measures clause reachability | met | CV-306 |  |  |
| AC-107 | entity metrics use semantic nearest-function ownership | met | CV-306, CV-310 |  |  |
| AC-108 | semantic points do not require dummy counters | met | CV-015 |  |  |
| AC-109 | normalized counter expressions remain sound under saturation | met | CV-017, CV-204 |  |  |
| AC-110 | point identity has one byte representation | met | CV-008 |  |  |
| AC-111 | coverage map 1.0 is closed and self-validating | met | CV-015, CV-018 |  |  |
| AC-112 | indexed evidence 1.0 is closed, self-contained, and reproducible | met | CV-222 |  |  |
| AC-113 | diagnostics are append-only, structured, and conservatively extensible | met | CV-009 |  |  |
| AC-114 | the version manifest is exact, deterministic, and sufficient for compatibility checks | met | CV-021 |  |  |
| AC-115 | the root compatibility policy is closed, pinned, and release-bound | met | CV-020 |  |  |
| AC-116 | the root submodule uses exact authenticated SSH acquisition and a pinned gitlink | met | CV-002 |  |  |
| AC-117 | doctor produces a complete deterministic aggregate from fixed probes | met | CV-022, CV-242 |  |  |
| AC-118 | the root driver provides one compatibility-governed coverage namespace | met | CV-032 |  |  |
| AC-119 | implementation selection is pinned, local, and policy-governed | met | CV-240, CV-241 |  |  |
| AC-120 | repository launchers resolve a qualified CPython deterministically | met | CV-031 |  |  |
| AC-121 | R1 Python execution has no third-party runtime dependency | met | CV-033 |  |  |
| AC-122 | canonical schemas generate reproducible dependency-free validators | met | CV-011 |  |  |
| AC-123 | canonical schemas use the closed Draft 2020-12 profile | met | CV-010 |  |  |
| AC-124 | the structural reference oracle is pinned, offline, and outcome-independent | met | CV-012 |  |  |
| AC-125 | the complete upstream suite is vendored and manifest-bound | met | CV-012 |  |  |
| AC-126 | one uv lock governs every non-runtime Python environment | met | CV-005 |  |  |
| AC-127 | non-runtime Python dependencies have one public source authority | met | CV-005 |  |  |
| AC-128 | one static Hatchling path produces exact reproducible distributions | partly met | CV-004, CV-243 | CV-413 |  |
| AC-129 | one static version identifies every R1 release surface | partly met | CV-004, CV-034 | CV-413 |  |
| AC-130 | SemVer progression reflects the highest public-contract impact | partly met | CV-034 | CV-413 |  |
| AC-131 | every release attachment has policy-bound verifiable provenance | owned |  | CV-411, CV-413 |  |
| AC-132 | release checksums, manifest, and SBOM reconcile exactly | owned |  | CV-411, CV-413 |  |
| AC-133 | protected publication requires independent approval | mismatch |  | owner, CV-413 | M5 |
| AC-134 | immutable publication locks the verified release | owned |  | CV-413 |  |
| AC-135 | retained releases remain recoverable and withdrawals remain controlled | owned |  | CV-413, CV-415 |  |
