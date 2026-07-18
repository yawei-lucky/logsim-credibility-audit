# Codex Workflow

> Current phase: strengthen the HUGSIM closed-loop evidence pipeline with
> scoped, reproducible, and reviewable tasks.

## Principle

Codex should help implement scoped experiments, collect evidence, and maintain
the repository. It should not independently decide the research direction or
make unsupported credibility judgments.

Research judgment remains with the Research Commander workflow:

```text
ChatGPT Research Commander -> research direction and final audit judgment
Codex -> scoped implementation, reproducible runs, evidence collection, documentation, and PR assistance
GitHub -> version control, issues, and review history
```

The current experimental carrier is HUGSIM. OmniDreams / Cosmos are deferred
until the HUGSIM evidence workflow is stronger or the Research Commander
explicitly changes the project direction.

## Good Codex Tasks at This Stage

### Task Type 1: Bounded evidence-pipeline work

Use Codex to:

- export synchronized RGB / semantic / depth evidence from recorded runs;
- run deterministic, bounded smoke tests using the project scripts;
- check state, rendering, and metric continuity;
- record reproducible commands, outputs, failures, and evidence limitations.

### Task Type 2: Markdown cleanup

Use Codex to:

- fix heading levels;
- keep section structure consistent;
- normalize TODO markers;
- check broken Markdown tables;
- remove accidental duplicated sections.

### Task Type 3: TODO tracking

Use Codex to:

- list all `TODO_SOURCE` items;
- group TODOs by file and section;
- create a small checklist for the next manual audit pass.

### Task Type 4: File structure maintenance

Use Codex to:

- ensure required files exist;
- keep README links synchronized;
- update the literature matrix after the Research Commander supplies verified entries.

### Task Type 5: PR assistance

Use Codex to:

- summarize PR changes;
- check whether a PR stays within scope;
- identify whether broad literature-review content was accidentally added.

## Bad Codex Tasks at This Stage

Do not ask Codex to:

- decide whether HUGSIM is globally credible or non-credible;
- invent citations or paper claims;
- produce a broad autonomous-driving simulator survey;
- expand to OmniDreams / Cosmos, a full HUGSIM benchmark, or a final
  quantitative credibility metric without an explicit project-direction change;
- upgrade evidence to `accepted` unless it satisfies
  `docs/hugsim_credibility_decision_rules.md`;
- replace `TODO_SOURCE` with unsupported claims.

## Starter Codex Prompt

```text
Task: Export synchronized RGB / semantic / depth comparison sheets from the
existing scene-0383 smoke run.

Scope:
- Use the existing observations.pkl.
- Keep generated images under artifacts/.
- Do not overwrite an existing run.
- Do not add dynamic actors or run the full benchmark.

Acceptance criteria:
- RGB / semantic / depth views are synchronized by camera and timestamp.
- Output generation is deterministic and reproducible.
- Concrete cross-modal observations and limitations are recorded.
- No global HUGSIM credibility claim is made.
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
