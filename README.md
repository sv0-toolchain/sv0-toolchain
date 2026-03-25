# sv0-toolchain

development workspace for the sv0 programming language compiler and toolchain.

## subprojects

| project | purpose | language | status |
|---|---|---|---|
| [sv0doc](sv0doc/) | formal language specification and wiki | markdown | milestone 0 |
| [sv0c](sv0c/) | bootstrap compiler (lexer through C backend) | SML/NJ | milestone 1 |
| [sv0vm](sv0vm/) | bytecode virtual machine interpreter | SML/NJ | milestone 2 |

## agent workflow

this workspace uses the [AI agent workflow structure](http://development.sasankvishnubhatla.net/tcowmbh/note/ai-agent-workflow-structure.html) to organize development work. agent files (`.Rmd`) in `task/` orchestrate implementation through directives and companion scripts.

### milestone structure

```
task/sv0doc-milestone-0.Rmd       milestone 0: extract formal specification
  ├── sv0doc-extract-grammar.Rmd      EBNF grammar
  ├── sv0doc-extract-type-rules.Rmd   type system rules
  ├── sv0doc-extract-contracts.Rmd    contract semantics
  ├── sv0doc-extract-memory-model.Rmd memory model
  └── sv0doc-extract-keywords.Rmd     keyword/operator reference

task/sv0c-milestone-1.Rmd         milestone 1: bootstrap compiler
  ├── sv0c-project-setup.Rmd          SML/NJ project scaffolding
  ├── sv0c-error-reporting.Rmd        error infrastructure
  ├── sv0c-lexer.Rmd                  tokenizer
  ├── sv0c-parser.Rmd                 recursive descent parser + AST
  ├── sv0c-name-resolution.Rmd        scope resolution
  ├── sv0c-type-checker.Rmd           type inference and checking
  ├── sv0c-contract-analyzer.Rmd      contract validation + runtime checks
  ├── sv0c-ir.Rmd                     intermediate representation
  └── sv0c-c-backend.Rmd              C99 code generation

task/sv0vm-milestone-2.Rmd        milestone 2: bytecode VM
  ├── sv0vm-bytecode-format.Rmd       instruction set + binary format
  ├── sv0vm-interpreter.Rmd           stack machine dispatch loop
  ├── sv0vm-runtime.Rmd               memory management + built-ins
  └── sv0vm-vm-backend.Rmd            sv0c VM backend (IR -> bytecode)
```

### running agents

```bash
# via CLI runner
.agent/runner.sh task/sv0c-lexer.Rmd

# dry run (show what would execute)
.agent/runner.sh --dry-run task/sv0c-milestone-1.Rmd

# via Cursor: open any .Rmd file and use /run-ai-tasks-in-doc
```

### dependency flow

```
sv0doc (specification)
  |
  v
sv0c (compiler)
  |
  ├── C backend (milestone 1)
  └── VM backend (milestone 2) ---> sv0vm (interpreter)
```

## design document

the language design is documented at:
<http://development.sasankvishnubhatla.net/tcowmbh/task/sv0-compiler-vision-and-design.html>

## directory layout

```
sv0-toolchain/
├── .agent/          agent infrastructure (runner, config, adapters)
├── .cursor/         cursor IDE integration (rules, commands)
├── lib/             shared scripts (shell utilities, SML helpers)
├── task/            agent workflow files (.Rmd) + companion scripts
├── sv0doc/          formal specification repository (git repo)
├── sv0c/            bootstrap compiler source (git repo)
└── sv0vm/           bytecode VM source (git repo)
```
