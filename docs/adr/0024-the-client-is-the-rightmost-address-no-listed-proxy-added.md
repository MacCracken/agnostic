# 0024 — The client is the rightmost address no listed proxy added

**Status**: Accepted
**Date**: 2026-11-06

## Context

TLS belongs to a reverse proxy, so behind one every request arrives from the proxy's address. The login
bucket is per source, so about 5 anonymous requests a minute locked out every login (audit S7). The
address a proxy passes on is in `X-Forwarded-For`, and any caller can write that header, so honouring it
from anyone lets a caller pick a fresh bucket per request and removes the limit.

## Decision

**`AGNOSTIC_TRUSTED_PROXIES` names who may say who the client is.** Unset, the header is ignored, as it
always was. Set, it is read only when the socket peer is on the list (`src/http/forwarded.cyr`).

**The client is the rightmost address that is not on the list.** A proxy appends what it saw, so the
right end is written by hops the operator trusts and everything to the left of the last one is the
caller's.

- **A token that does not parse ends what can be believed**, and the answer falls back to the proxy, so
  the caller shares the proxy's bucket and gains nothing.
- **Every line of the header counts.** nginx folds a client's header into one line, HAProxy adds a line
  after the client's, and `sandhi_server_find_header_a` answers the first, which is the client's. So the
  raw request is read, and repeated lines count as one value in order (RFC 9110 §5.3).
- **An IPv6 client is its /64.** A host usually holds a whole /64, so a bucket per address would give each
  caller 2^64 of them.
- **A list entry is refused rather than guessed at:** `/0`, host bits under a mask, a leading zero.

## Consequences

- **Positive** — one client's bad logins no longer lock out everyone behind the proxy, and the audit trail
  names the client and not the proxy.
- **Negative** — anyone on the list can claim to be any client, so the list has to be exact. `/0` is
  refused because it would hand that to every caller.
- **Neutral** — the list is IPv4, because the socket peer it is compared with is: sandhi's server binds
  AF_INET. An IPv6 address in the header is a client, or a hop treated as one.

## Alternatives considered

- **The leftmost address.** What most examples show. It is the one the caller writes.
- **A count of hops** in place of a list. Right until the topology changes, and then silently wrong in
  the direction that gives every caller their own bucket.
- **`Forwarded` (RFC 7239) as well.** Two headers are two chances to disagree, and every proxy in use can
  write this one.
