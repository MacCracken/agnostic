# 002 — The dependency pins

**Since**: 0.1.18, when these notes moved out of `cyrius.cyml`

`cyrius.cyml` is the compiler's configuration. This note holds the constraints on what it says,
which a reader cannot get from the file. Current versions are in
[`state.md`](../development/state.md), and what moved at each release is in `CHANGELOG.md`.

## The Cyrius pin and the dep tags are one change

`cyrius lib sync --full` fills `lib/` from the pinned toolchain's stdlib snapshot, and that snapshot
folds first-party libraries, sigil and patra among them. `cyrius deps` then resolves the dep chain
on top of it.

- **The chain must declare exactly the folds.** `cyrius deps` will not replace a folded file, so
  `lib/` keeps the fold's bytes and the lock's commit pin names whatever the chain declared.
  `scripts/check-clean.sh` allows no file in `lib/` to differ from the snapshot. A chain that
  declares a sigil or patra the pin does not fold is wrong in either direction, and a
  `[deps.patra]` hold here or an allowance in that gate does not fix it.
- **The compiler moves too.** A release can refuse what an older dep's `dist/` bundle contains, so
  a pin bumped alone can break `lib/` with `src/` untouched. Going the other way, a dep moved alone
  can need a toolchain the pin does not provide.
- **Take each sibling's release on the pin's line, not its latest tag.** Siblings keep releasing on
  newer toolchains. Read the sibling's own `cyrius.cyml` at the tag (`git show <tag>:cyrius.cyml`).
  The agnosai tag decides most of the rest, as below.

`cyrius deps` prints `refusing to overwrite stdlib leaf 'sigil'` and `'patra'` on every resolve.
That is expected: the warning names the skipped artifact, which is the fold's own bytes when the
chain declares the folds. Hash it against the tag if in doubt.

## Tags only, never `path`

`path` beats `tag` when a checkout is present, so a local resolve vendors the sibling's work in
progress into `lib/` and the lock. That content matches no tag, and CI cannot fetch it. This holds
for this manifest only: a `path` in a dep resolved from the cache points into the cache and is
inert.

## agnosai's deps are pinned by agnosai

bote, majra, kavach, ai-hwaccel and tyche arrive through agnosai, and this file carries no pins for
them. A `[deps.X]` block here is an override, even with no `modules`: such a block means
`modules = ["dist/X.cyr"]`, and the root's tag wins. To move one of them, release agnosai and
re-pin it.

## Two root blocks, in this order

`libro` is declared here because `src/engine/audit.cyr` calls it directly. Reaching it only through
agnosai and bote would let a bote that dropped it take the audit chain away, and would leave its
version to whatever bote pinned.

It comes after `[deps.agnosai]` on purpose. The root manifest resolves first, then each dep's own
deps breadth-first in manifest order, and the first declaration of a name wins. agnosai declares
the sigil fold. Listed first, libro's sigil would be the one the lock records whenever the two
differ.

Each block needs `modules`, or it is not the dep it looks like (above).

## `[deps] stdlib` lists what `src/` uses

Every stdlib leaf this code calls is listed, even when something else would bring it in: a dep's
`.deps` sidecar names only what that dep's own bundle needs, so a leaf that arrived that way can
disappear at a re-pin. A failed build names the missing leaf.

- `sigil` is the crypto tier: Argon2id, SHA-256 and HMAC-SHA256. agnosai also brings it, and the
  entry keeps an agnosai that stopped depending on it from taking the crypto tier away from the
  identity surface. Constant-time compare is `ct_eq_bytes`, in `ct`.
- `patra` is the embedded store. It is folded into the snapshot, so it is a stdlib entry. libro is
  not folded, so it is a git dep.

## Both release targets are required

`bins` is the native x86_64 build and `cross_bins` is what the release workflow cross-compiles.
`first-party-standards.md` makes both x86_64-linux and aarch64-linux artifacts a release-checklist
item, so aarch64 stays in `[release]` and every suite runs natively on real hardware at a pin move.
