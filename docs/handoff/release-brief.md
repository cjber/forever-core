# Release brief (read with brief.md; brief.md's commit/PR/merge rules still apply)

The owner has authorised releases ("cut releases when happy with all"). You prepare ONE addon's release.

## Phase 1: prepare (you do this now)
1. Read the repo's AGENTS.md and `.agents/skills/release/SKILL.md` in full, plus the skills it names in
   /home/user/skills (wow-forever-addon incl. check_copy.py and voice.md, wow-addon-publish, copywriting,
   wow-mock-screenshots). Follow the skill exactly, except for the limits below.
2. From fresh origin/main, check the data-refresh state as the skill says (open data PRs, failure issues,
   whether pins are newest). If a refresh is needed, run it through the documented generator and include it.
3. Choose the version from the changes since the last tag (minor bump for new features; justify it).
   Move `[Unreleased]` notes into `## [X.Y.Z] - 2026-10-15` (use today's UTC date when you finish), keeping
   an empty `[Unreleased]`. Notes are prose with bold-lead bullets in the owner's plain voice. API changes
   go under `### For addon authors`. Edit the accumulated bullets into a coherent entry: merge duplicates
   and drop internal-only noise. Run `tools/changelog.py --check X.Y.Z` and `--check`.
4. Bring README.md and docs/curseforge.md up to date with everything that shipped, in the owner's voice,
   never marketing. Run check_copy.py on both and keep within the length limits.
5. Re-render screenshots twice (byte-identical) per the skill, commit them with the manifest/scenes.sha256, and
   inspect the changed images.
6. Write the store plan (summary, description, logo, gallery files with captions and order, and stale images
   to remove) to /tmp/claude-0/-home-user/76bf530e-5da5-583c-877f-df32f2ad82fa/scratchpad/release/<repo>-store.md.
   No browser or store connector is available in this session, so the owner applies these by hand.
7. Open the release PR (`chore: prepare vX.Y.Z`) with the full gate passing. Get it green and up to date with main,
   run code-review (high), then send `READY <url> <sha>` to "main", and include the version and the changelog
   entry text in that message.
8. Stop there, and end with a report: the version, the changelog text, the consolidated /reload checklist for
   this release (from the CHANGELOG and the merged PRs' in-game sections), and the store plan path.

## Phase 2: publish (only when the coordinator resumes you and says "publish")
- A cloud session cannot push tags. The coordinator starts the Release workflow on main (workflow_dispatch with
  `version`) after ci.yml passes on main at the release commit.
- Then you verify, per the skill: watch the release run, confirm both store IDs show `[token set]` and uploads
  succeeded, download and inspect the GitHub release zip, and check the CurseForge/Wago public pages
  (report moderation as pending with its URL). Report links.

## Limits
- Never merge, push tags or trigger workflows yourself. Never print secrets.
- Leave unrelated open issues alone.
