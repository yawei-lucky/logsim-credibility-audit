# Codex Workflow

> Current phase: keep Codex tasks simple, mechanical, and reviewable.

## Principle

Codex should help maintain the repository. It should not independently decide the research direction.

Research judgment remains with the Research Commander workflow:

```text
ChatGPT Research Commander -> audit judgment and source-grounded text
Codex -> file editing, formatting, TODO tracking, and PR assistance
GitHub -> version control, issues, and review history
```

## Good Codex Tasks at This Stage

### Task Type 1: Markdown cleanup

Use Codex to:

- fix heading levels;
- keep section structure consistent;
- normalize TODO markers;
- check broken Markdown tables;
- remove accidental duplicated sections.

### Task Type 2: TODO tracking

Use Codex to:

- list all `TODO_SOURCE` items;
- group TODOs by file and section;
- create a small checklist for the next manual audit pass.

### Task Type 3: File structure maintenance

Use Codex to:

- ensure required files exist;
- keep README links synchronized;
- update the literature matrix after the Research Commander supplies verified entries.

### Task Type 4: PR assistance

Use Codex to:

- summarize PR changes;
- check whether a PR stays within scope;
- identify whether broad literature-review content was accidentally added.

## Bad Codex Tasks at This Stage

Do not ask Codex to:

- decide whether OmniDreams is credible;
- invent citations or paper claims;
- produce a broad autonomous-driving simulator survey;
- merge NeuroNCAP / HUGSIM / UniSim / AdvSim into the main audit before OmniDreams v0.1 is complete;
- replace `TODO_SOURCE` with unsupported claims.

## Starter Codex Prompt

```text
Task: Clean up the Markdown structure for docs/omnidreams_audit.md.

Scope:
- Do not add new research claims.
- Do not remove TODO_SOURCE markers.
- Do not expand into a literature review.
- Keep the section structure focused on OmniDreams credibility audit.

Acceptance criteria:
- Markdown headings are consistent.
- Every main section keeps: Paper Claim, Evidence Provided, Audit Judgment, Open Questions.
- No unsupported factual claims are added.
- The document remains focused on OmniDreams.
```

## Later, after the workflow is stable

Possible future automation:

```text
GitHub issue with label: codex-task
  -> Codex runs a mechanical repo-maintenance task
  -> Codex opens a PR
  -> Research Commander reviews the PR
  -> Human decides whether to merge
```
