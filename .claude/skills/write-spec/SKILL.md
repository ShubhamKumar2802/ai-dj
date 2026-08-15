---
name: write-spec
description: >
  Draft, amend, or version a module spec in this repo's spec-driven workflow.
  Use this whenever the user wants to design a new module, formalize an
  architecture or design discussion into a spec before any code is written, or
  change behavior that already has a spec — a bug fix, a code-review finding, a
  design rethink — since in every one of those cases the spec changes before the
  code does. Also use when the user asks where specs live, how to name or store
  a spec file, or whether a change to an existing spec is an amendment or needs
  a new version.
---

# Writing a spec in this repo

This repo is spec-driven (see `CLAUDE.md`): code implements the spec, never the
other way around. This skill exists so that fact gets applied the same way every
time, instead of being re-derived in conversation each time it comes up — which is
exactly what happened before this skill existed, and took several rounds of back-
and-forth to settle.

**Full naming, storage, and amendment/versioning rules live in
`resources/documentation/README.md` — read it before drafting or amending any spec.**
Don't restate its rules here from memory; if this skill and that file ever disagree,
the README wins and this skill should be corrected to match, not the reverse.

## The loop

1. **Propose.** A module needs a spec — a new build-order item, or a design gap
   surfaced during implementation, code review, or later maintenance.
2. **Draft in Plan Mode.** The spec *is* the plan's deliverable — write it to its
   pinned path (`resources/documentation/<layer>/<module>/spec.md`, per the README)
   as part of the plan itself, not as a follow-up after the plan is approved. Pin
   every file the spec expects to exist under `src/` and `tests/` before any of them
   are written — an implementer should never have to guess a path, a signature, or a
   field name.
3. **Get approval before any code exists.** Exiting plan mode with an approved spec
   is the gate — nothing under `src/` gets written until the spec it implements is
   approved.
4. **Implement strictly to the approved spec.**
5. **If reality forces a deviation** — during implementation, review, or later
   maintenance — stop. Work out whether it's an amendment or a new version (the
   README's decision table), update the spec, get it approved, *then* resume code.
   Never let code and spec drift silently — that failure mode is the whole reason
   this workflow exists.

## When drafting

Match the house style already established by `resources/ai-dj-design-v3.md` and
`resources/documentation/common/llm_service/spec.md`: numbered sections, an
explicit invariant stated up front where the module has one, pseudocode-style
schema blocks with every field typed and commented (no field left implicit), and a
"rejected alternatives" table when the design ruled out real alternatives worth
recording so they aren't re-litigated later.

Pull requirements from the actual conversation, not from assumption — if the scope
of a module is ambiguous (what it owns vs. what a consumer owns, whether something
is v1 or deferred, which files it touches), ask before writing it into the spec as
settled.
