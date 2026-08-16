# Git convention

A terminal-first runbook for how work moves through this repo: branch → commits →
PR → review → merge → (eventually) release. Each step explains *why* before
showing the command, so this doubles as a place to actually learn the workflow, not
just copy commands blindly.

Applies to module implementation work — one `feature/*` branch per module,
matching `resources/documentation/overview.md`'s build-order rows. Trivial doc-only
fixes can skip straight to a `dev` commit if that's ever the call; everything else
below is the default.

---

## 1. How this repo's branches work

Two long-lived branches, plus short-lived ones:

- **`main`** — releases only. Nothing is committed here directly; it only moves
  when `dev` is deliberately promoted (§6).
- **`dev`** — the integration branch. Always buildable (tests + lint pass). Every
  module's work lands here first, one at a time.
- **`feature/<layer>-<module>`** — one per module, branched from `dev`, merged back
  into `dev`, then deleted. Lives only as long as that module takes to build.

Why this shape: `dev` gives a safe place to land module-by-module work without
every single commit needing to be release-ready — you can be mid-way through
`edge_builder` with `dev` still in a good state from `cue_derivation`. `main` only
reflects deliberate releases, not day-to-day progress.

Confirm the current setup any time with:

```bash
git remote -v
git branch -a
```

---

## 2. Prerequisite: install `gh`

Everything below — opening PRs, merging, even branch protection — is done from the
terminal via GitHub's CLI, not the website. It isn't installed on this machine yet:

```bash
brew install gh
gh auth login
```

`gh auth login` walks through browser-based auth once; after that every `gh`
command in this doc works straight from the terminal.

---

## 3. Branch naming

```
feature/<layer>-<module>
```

`<layer>` and `<module>` come straight from `resources/documentation/overview.md`'s
rows — e.g. `feature/ingestion-feature-extractor`,
`feature/render-transition-renderer`, `feature/processing-edge-builder`. Keeps the
branch name traceable to exactly one spec and one row in the tracker.

---

## 4. Full workflow, one module at a time

### 4.1 Start from an up-to-date `dev`

Always branch from the latest `dev`, not whatever your local copy happened to be
last time you looked:

```bash
git checkout dev
git pull
git checkout -b feature/ingestion-feature-extractor
```

### 4.2 Work in small, buildable commits

Each commit should stand on its own — build, and ideally pass tests. This is what
makes `git bisect` useful later (binary-searching commits to find where a bug was
introduced only works if every commit in between is actually runnable), and it
keeps the eventual PR diff reviewable in pieces rather than one wall of change.

```bash
git add src/ingestion/feature_extractor/schema.py
git commit -m "feat: add RawFeatures and PerBarFeatures schema"

git add src/ingestion/feature_extractor/loader.py tests/ingestion/feature_extractor/test_loader.py
git commit -m "feat: add canonical-format audio loader"
```

See §5 for the commit prefix convention (`feat:`, `test:`, etc.).

### 4.3 Rebase on `dev` before pushing

Not merge — rebase. `dev` has likely moved since you branched (other modules
landing). Replaying your commits on top of the latest `dev` keeps history linear —
one straight line of commits instead of a merge bubble — and surfaces any conflict
with `dev` *now*, while the change is fresh in your head, instead of days later at
PR time.

```bash
git fetch origin
git rebase origin/dev
```

If it conflicts: git will pause on the offending commit, mark the conflicted files.
Fix them, then:

```bash
git add <resolved files>
git rebase --continue
```

(`git rebase --abort` bails out and restores things to before the rebase, if it
gets messy.)

### 4.4 Run checks locally

Same commands `CLAUDE.md` already names for this project — reused here, not
reinvented:

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

All three clean before pushing — this is what "always buildable" in §1 actually
means in practice.

### 4.5 Push with upstream tracking

```bash
git push -u origin feature/ingestion-feature-extractor
```

`-u` sets the branch to track `origin/feature/ingestion-feature-extractor` — every
`git push`/`git pull` on this branch after this needs no arguments. (After a
rebase, if you'd already pushed once before, you'll need
`git push --force-with-lease` instead — `--force-with-lease` refuses the push if
someone else also pushed to the branch in the meantime, unlike a bare `--force`
which would silently clobber their work.)

### 4.6 Open a PR from the terminal

```bash
gh pr create --base dev --title "Add ingestion/feature_extractor" \
  --body "Implements resources/documentation/ingestion/feature_extractor/spec.md"
```

`gh pr create` without flags also works interactively — it'll prompt for title/body
and let you pick the base branch.

### 4.7 Review

```bash
gh pr view --web    # optional, if you want to see the PR's diff rendered
```

Run `/code-review` against the branch before merging. Address anything it finds
with more commits on the same branch, then re-push:

```bash
git add -A
git commit -m "fix: address review feedback on downbeat confidence calc"
git push
```

### 4.8 Merge from the terminal

```bash
gh pr merge --squash --delete-branch
```

**Squash**, not a plain merge commit: it collapses every commit on the
branch — including the "fix: address review feedback" ones — into one clean commit
on `dev`. The WIP history was useful *during* review; once merged, one commit per
module is what actually helps someone reading `dev`'s history later. `--delete-branch`
removes the branch on GitHub immediately after merge.

### 4.9 Sync your local copy

```bash
git checkout dev
git pull
git branch -d feature/ingestion-feature-extractor
```

`-d` is the *safe* delete — it refuses if the branch has commits `dev` doesn't
have yet (i.e. it isn't actually merged). If you're ever certain you want to
discard a branch's commits anyway, `-D` forces it — don't reach for that by
default.

### 4.10 Update the tracker

```bash
# edit resources/documentation/overview.md — flip this module's Code column to Done
git add resources/documentation/overview.md
git commit -m "docs: mark ingestion/feature_extractor implemented"
git push
```

(You're on `dev` at this point, per §4.9, so this commits straight there — no
branch needed for a one-line tracker update.)

---

## 5. Commit message convention

Conventional-commit-style prefixes:

| Prefix | When |
|---|---|
| `feat:` | New capability — a new function, module, endpoint |
| `fix:` | Bug fix |
| `test:` | Test-only change (new tests, fixing a flaky test) |
| `docs:` | Documentation only (specs, this file, `overview.md`) |
| `refactor:` | Code restructuring with no behavior change |
| `chore:` | Everything else — dependency bumps, config, tooling |

Why bother: `git log --oneline` becomes scannable by category, and it maps cleanly
onto what actually changed without opening the diff. This repo's existing history
(`git log`) already uses plain imperative subjects ("Add commom llm service and
logger") — this convention formalizes that same imperative-mood habit with an
explicit category prefix, it doesn't replace the style.

---

## 6. Releasing `dev` → `main`

Periodic, not per-module — once several modules are stable together.

```bash
gh pr create --base main --head dev --title "Release: ingestion + render layer"
gh pr merge --merge
```

**Plain merge here, not squash** — the opposite choice from §4.8, deliberately.
Squashing a whole release into one commit on `main` would throw away the individual
module commits `dev` already accumulated; a real merge commit preserves them in
`main`'s history while still marking the exact point a release happened.

Optional: tag the release.

```bash
git tag -a v0.2.0 -m "ingestion + render layer, walking skeleton"
git push origin v0.2.0
```

A tag is a fixed, named pointer to that commit — `git checkout v0.2.0` always gets
you back to exactly this state, and `git describe` can report "how far past the
last release" any later commit is.

---

## 7. Optional: enforce this from the terminal (branch protection)

Everything above is a convention you follow — nothing stops a direct push to `dev`
or `main` unless you turn on branch protection. Doing that from the terminal
instead of GitHub's Settings page:

```bash
gh api repos/ShubhamKumar2802/ai-dj/branches/dev/protection -X PUT --input - <<'EOF'
{
  "required_status_checks": null,
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0
  },
  "restrictions": null
}
EOF
```

This requires changes to land via PR (no direct push), even without a second
reviewer (`required_approving_review_count: 0` — there's no one else to review a
solo project's PRs). Once CI is wired up, add a `required_status_checks` block
naming the check(s) that must pass first. Repeat for `main` by swapping the branch
name in the URL. This is one-time setup, optional, and doesn't need repeating per
module.

---

## 8. Quick reference

Once the concepts above are familiar, the whole loop condensed:

```bash
# start
git checkout dev && git pull
git checkout -b feature/<layer>-<module>

# ...work, committing as you go...

# before pushing
git fetch origin && git rebase origin/dev
uv run pytest && uv run ruff check . && uv run ruff format .

# push + PR
git push -u origin feature/<layer>-<module>
gh pr create --base dev --title "..." --body "..."

# after review passes
gh pr merge --squash --delete-branch

# sync up
git checkout dev && git pull
git branch -d feature/<layer>-<module>

# mark it done in resources/documentation/overview.md, commit, push
```
