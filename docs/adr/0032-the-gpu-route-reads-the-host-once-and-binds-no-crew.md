# 0032 — The GPU route reads the host once, and binds no crew

**Status**: Accepted
**Date**: 2026-11-06

## Context

The former code had five GPU routes (G10), over `nvidia-smi` on a 30-second cache. Two things were wrong with
the first idea of a route here, which was to say what a crew's `gpu_required` can find on this host.

**`gpu_required` does not look at the host.** agnosai scores it against an agent's GPU flags
(`agnosai_gpu_score`). `agnosai_hw_inventory_satisfies` exists and has no caller in the run path. So a crew
that needs a GPU runs on a host with none. Inference also happens at the gateway, usually on another
machine, so this host's GPU is rarely the one a crew uses.

**Detection is not a thing to run per request.** `ai-hwaccel` allocates on the global heap, spawns vendor
tools, and sets the process-wide subprocess timeout while it runs.

## Decision

**One route, `GET /api/v1/gpu`, at READ, over a snapshot taken at mount.** On the one thread, before the
server listens, so no request touches the hardware and anyone may ask as often as they like.

**`gpu_required_enforced` is on every answer, and false.** The same reason as `crews_call_tools`: a list of
GPUs beside a `gpu_required` field reads as though one governs the other.

**It keeps only what stays true:** type, name, driver, size, and whether the memory is the host's own. Free
memory, utilization and temperature change by the second, and a snapshot of them is a stale number
presented as a reading. `detected_at` says when it was taken.

**No subprocess unless the operator asks.** agnostic spawns nothing today, and a sandbox can refuse `execve`.
By default detection is sysfs alone, which sees AMD, Intel, Vulkan and NPUs and not NVIDIA, whose source is
`nvidia-smi`. `AGNOSTIC_GPU_TOOLS=on` runs the tools. `vendor_tools` on the answer says which it was, so an
empty list on an NVIDIA host does not read as no GPU. A value that is neither word refuses to start, so a
`yes` is not read as no.

**A tool's words stay in the log.** They can hold paths and driver text, and READ gets a count. A tool that is
not installed is INFO and is not counted: every host lacks most vendors' tools, and a count that is never 0
is one nobody reads.

**One route, where there were five.** Status, one device and memory are this list. Cross-crew slots and local
inference wait on something that places work on a GPU, which nothing here does. There is no `force`, because
no request reads the hardware.

**Fleet has no route.** Nothing feeds one, and agnostic is one process on one database, so it would answer
empty for ever. It comes with a fleet (roadmap, Settled decisions, 2026-11-06).

## Consequences

- **Positive** — a READ route costs an arena and cannot start a process or hold a worker.
- **Negative** — a card added or lost while the server runs is not seen until a restart.
- **Negative** — with tools on, a tool that hangs holds up the start by ai-hwaccel's deadline: 21 s measured,
  per hung tool, after which it is killed and the server comes up. A slow start is the cost of the tools
  being the operator's choice, and it beats a route that holds a worker.
- **Negative** — `PrivateDevices=true`, which the example unit sets, gives the server a private `/dev`. Sysfs
  detection does not read `/dev`, so an AMD GPU is still listed under it (measured). A vendor tool that opens
  a device node cannot work there, so `nvidia-smi` needs it off. That half is expected and not measured: no
  NVIDIA card was to hand.
- **Negative** — an empty list means this read found none, not that the host has none. A Raspberry Pi 4 reads
  empty: `ai-hwaccel` does not count its V3D as an accelerator.
