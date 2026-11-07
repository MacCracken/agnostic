# 0036 — A package is JSON, and all of itself or none

**Status**: Accepted
**Date**: 2026-11-06

## Context

The former `.agpkg` is a ZIP holding a manifest, definitions, presets and tool modules, and agnosai has a port
of it (`agnosai_package_export`, `_import`). The roadmap asked for package export and import, and the obvious
move was to mount agnosai's. Reading it found three things:

- Its package holds engine agents, which have no slot for `focus` or `allow_delegation`, so a definition would
  lose them on the way through, silently.
- It allocates on the global heap with nothing to give back, on a route anyone with write access can call.
- It brings an archive reader and a compressor to a door where the body cap already bounds the document.

And two things about the former import: it took each file that parsed and reported the rest in `errors`, so a
package could land half-installed, and it wrote presets, which here are compiled in.

## Decision

**A package is one JSON document**: `{"format":"agnostic-package/1","name","version","exported_at","definitions":[…]}`,
each definition in the form a definition already has. So it takes the same door, carries what the engine does not,
and needs no new parser. `format` says which form it is, should another ever be wanted, and any other value is a
422.

**Export takes a name and an optional list of keys**, and is READ: it says nothing a `GET` would not. It is a POST
for that list. With no list it is all of the caller's tenant.

**Import is all or none.** Every definition goes through the door, and every conflict is found, before anything
is written. A key already stored is a 409 naming all of them, unless `?overwrite=true`, and a key twice in one
package is a 422. It is WRITE, and goes through the ordinary write, so each definition gains a version and what
it replaced can be got back.

**A package lands in the importer's tenant**, whoever exported it. Nothing in it names a tenant.

**At most 256 definitions.** A package must fit a request body anyway, 1 MiB by default.

## Consequences

- **Positive**: moving a tenant's agents between deployments is two requests, and the document can be read and
  diffed.
- **Negative**: not interoperable with an `.agpkg`. Nothing in this ecosystem produces one today.
- **Negative**: "none" stops at the write. There is no transaction to run an import in, so a failed write part
  of the way leaves some of it, and the 500 lists what went in.
- **Not done**: a package carries no signature, so importing one means trusting whoever sent it. What it holds
  reaches a model when a crew runs it, so that is a real trust decision, made by whoever has WRITE.
- **Not done**: presets and tools do not travel. The library is compiled in, and tool upload waits for a sandbox.
