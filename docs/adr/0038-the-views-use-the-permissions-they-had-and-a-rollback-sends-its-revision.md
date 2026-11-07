# 0038 — The views reach the new routes through the permissions they had, and a rollback sends its revision

**Status**: Accepted
**Date**: 2026-11-06

## Context

0.4.2 added definition versions, packages, a crew's `team` and a preset recommendation as routes, and nothing in
the shell could reach them. A plugin reaches a route only through a permission in `src/webgui/permissions.json`
([ADR 0007](0007-plugin-requests-are-checked-by-the-server.md)), and the shell forwards `If-Match` only on a PUT or a
DELETE, while a rollback is a POST. And the Crews view could not start a crew at all: it listed and cancelled them.

## Decision

**The new routes join the permissions that already say what they do.** A new name for each would be four more lines
in Settings for one meaning.

| Permission | Gains |
|---|---|
| `definitions:read` | `GET …/versions`, `GET …/versions/:n`, `POST /api/v1/packages/export` |
| `definitions:write` | `POST …/rollback`, `POST /api/v1/packages/import` |
| `presets:read` | `POST /api/v1/preset-recommendations` |

**A `:read` permission can hold a POST.** The server's own permission on those routes is READ: a POST there is how a
long argument travels, and it writes nothing.

**The shell forwards `ifMatch` on a POST.** A rollback writes over what is current, as a PUT does, and from a stale page
it must be refused for the same reason. Forwarding it does nothing to a route that does not read it.

**The Crews view gains `presets:read`,** to ask which preset fits and to read a preset's roles. It gains nothing that
reads a definition: the team is assembled at the server's door, as the signed-in user.

**The composer sends a `team`, and only ever a `team`.** A crew spelled out agent by agent is Swarm Command's. This view
says who the crew needs, and shows who it became, so the plan's agents are now on every crew's page.

**A deleted definition is reached by its link.** The list shows what exists, and adding the deleted to it would make
every reader filter them out. Deleting offers the way back at once, and `#plugin/library?tab=definitions&item=<key>`
reaches it later.

**A package over the bridge's 256 KB is refused in the view,** saying which route takes it. The server's own limit is
1 MiB, and raising the bridge's for one route would loosen it for every plugin.

## Consequences

- **Positive**: a person can undo an edit, recover a deletion and start a crew without writing a request.
- **Positive**: an old shell with a new page answers 400 to a rollback's `ifMatch` rather than dropping it, so a tab left
  open across an upgrade is refused and not unprotected.
- **Negative**: a plugin that holds one of these permissions gains the new routes without its manifest changing, and
  Settings shows new words for an old name. All five plugins are built in, so nobody else's plugin is widened, and a
  plugin's permissions are still the most it can do, never more than its user can.
- **Negative**: Swarm Command holds `presets:read`, so it can ask for a recommendation it does not use.
- **Limit**: the view's own checks repeat a few of the server's bounds on a team, so that a slip is caught at the field.
  The server stays the door, and a bound that moves there goes stale here until the page is changed.
