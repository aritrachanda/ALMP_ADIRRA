## Context

The app has a session role model (`frontend/src/stores/roleStore.ts`) with four roles —
`data_analyst`, `data_architect`, `data_steward`, `business_user` — described in-code as
"lightweight, non-enforced … NO access enforcement yet". No FastAPI route uses a role/permission
dependency; roles appear only as optional audit/provenance strings. The reference-data read
endpoints therefore have no gate. Phase 5 adds one that is consistent with this prototype (light,
default-allow) rather than introducing a full auth stack.

## Goals / Non-Goals

**Goals:**
- Add a real, testable read-access check on the reference-data read endpoints.
- Reuse the existing four-role vocabulary; keep reading broadly allowed.
- Close the reference-data test gaps (per-field GET/PATCH, gate behaviour).

**Non-Goals:**
- A full authentication system, sessions, tokens, or user identity.
- Enforcing write-side roles (binding/meanings/status remain as today).
- Making the frontend send a role header (the default-allow path keeps it working).
- Restricting any role from reading (all four roles may read).

## Decisions

**D1 — Gate via an optional `X-Role` header, default-allow.**
A `require_read_access` FastAPI dependency reads an optional `X-Role` header, lower-cases/trims it,
and permits any value in the known-role set. When the header is absent it defaults to
`data_analyst` (a reader) and passes. Only an explicitly present but unknown role yields 403. This
mirrors the frontend vocabulary, is trivially testable, and cannot break existing callers that send
no header. *Alternative rejected:* a full auth dependency / token check — disproportionate for a
prototype with no identity layer and would over-restrict.

**D2 — Broadly allow: every known role may read.**
The Reference Dataspace is a read-only register; there is no reason to hide it from any role. The
gate validates the role rather than differentiating capabilities, matching the phase instruction
("reading should be broadly allowed; do not over-restrict"). *Alternative rejected:* per-role read
tiers — unnecessary complexity and risks over-restriction.

**D3 — Keep the store's plain GET (no header) working.**
The read-only frontend store issues bare `fetch('/api/reference-data')` calls (guarded by a test
that forbids request-init objects). Default-allow means no frontend change is needed and that test
stays green. If a client *does* send `X-Role`, it is validated.

**D4 — Fill test gaps against real endpoint behaviour.**
Add focused tests for the per-field `GET`/`PATCH` (codes, status, bound-set resolution, meanings
persistence) and for the gate (no header → 200, known role → 200, unknown role → 403), rather than
relying on indirect coverage through the aggregate.

## Risks / Trade-offs

- **Perceived security theatre** → a default-allow gate is not authentication. *Mitigation:* it is
  scoped and documented as a light validation seam for a prototype; it establishes the dependency
  that a real auth layer can later tighten, without over-restricting now.
- **Unknown-role 403 could surprise a mis-typed client** → *Mitigation:* only an explicitly present
  bad role is rejected; the common no-header path always passes.

## Open Questions

- Should the write path (bind/meanings/status) later require an editor role
  (`data_analyst`/`data_architect`/`data_steward`, not `business_user`)? Deferred — out of scope for
  this read-focused hardening pass.
