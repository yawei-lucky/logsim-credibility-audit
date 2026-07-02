# Source Availability Gate

This file defines the standard source-availability checklist used before auditing any log-driven counterfactual closed-loop simulation paper.

The purpose is to distinguish **paper-reported evidence** from artifacts that can be independently inspected, executed, or reproduced.

## Gate Template

| Item | Status | Evidence | Audit Consequence |
|---|---|---|---|
| Paper | Available / Missing | link | Can cite paper claims |
| Project page | Available / Missing | link | Can inspect demos / claims |
| Code repo | Available / Missing | link | Can verify implementation |
| Model weights | Available / Missing / Gated | link | Can or cannot reproduce generation |
| Dataset | Available / Missing / Restricted | link | Can or cannot verify training/eval distribution |
| Simulator runtime | Available / Missing | link | Can or cannot run closed-loop tests |
| Policy agent | Available / Missing | link | Can or cannot reproduce agent interaction |
| Orchestrator | Available / Missing | link | Can or cannot reproduce state update |
| Evaluation scripts | Available / Missing | link | Can or cannot reproduce reported metrics |

## Usage Rule

Before writing a simulator credibility audit, complete this gate first.

Do not treat a paper as externally auditable merely because the paper exists. A paper can support claims about what the authors report, but reproducibility and independent credibility auditing require public artifacts such as code, model weights, runtime environment, datasets, policy agents, orchestrators, and evaluation scripts.

## Status Vocabulary

Use these status values consistently:

- `Available`: publicly accessible and usable for audit.
- `Missing`: no public artifact found.
- `Gated`: access exists but requires approval, login, license acceptance, or special permission.
- `Restricted`: artifact exists but cannot be freely inspected or redistributed.
- `TODO_NOT_CONFIRMED`: not yet checked carefully enough.

## Audit Consequence Rule

If an item is `Missing`, `Gated`, `Restricted`, or `TODO_NOT_CONFIRMED`, explicitly state what kind of credibility claim cannot be independently verified.

Example:

```text
If simulator runtime is missing, reported closed-loop results remain paper-reported evidence rather than externally reproducible evidence.
```
