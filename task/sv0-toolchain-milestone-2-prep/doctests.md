# sv0 doctests (milestone 2 prep)

Policy:

- Fenced blocks use the marker `sv0 doctest` so `scripts/sv0_doctest.py` can find them.
- Attributes on the opening fence: `name=...` (label), `expect_exit=N` (default `0`).
- Each block must be a full program with `fn main() -> i32` or `-> unit` (VM path uses integer exit codes; `unit` main exits `0`).
- Runner: `python3 scripts/sv0_doctest.py --root <toolchain-root> <this-file>...`

Arithmetic sanity:

```sv0 doctest name=add expect_exit=4
fn main() -> i32 {
  return 2 + 2;
}
```

Let binding:

```sv0 doctest name=let_mul expect_exit=42
fn main() -> i32 {
  let x: i32 = 6 * 7;
  return x;
}
```
