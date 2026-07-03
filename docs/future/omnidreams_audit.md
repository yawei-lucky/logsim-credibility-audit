# OmniDreams Credibility Audit

> Status: working draft skeleton with source availability gate.  
> Scope: audit OmniDreams' self-evidence mechanism, not a general paper summary.

## Source Availability Gate

This gate must be completed before treating a simulator paper as externally auditable. It distinguishes paper-reported evidence from artifacts that can be independently inspected or reproduced.

### Availability Table

| Item | Status | Evidence | Audit Consequence |
|---|---|---|---|
| OmniDreams paper | Available | https://arxiv.org/abs/2606.03159 | Paper claims can be cited and audited as reported evidence. |
| OmniDreams PDF / TeX source | Available via arXiv | https://arxiv.org/abs/2606.03159 | Useful for extracting claims, figures, tables, and exact wording. |
| OmniDreams official project page | TODO_NOT_CONFIRMED | TODO_SOURCE | Do not assume a public product or demo page exists. |
| OmniDreams official code repository | TODO_NOT_CONFIRMED | TODO_SOURCE | Cannot verify implementation details from public code yet. |
| OmniDreams model weights / checkpoints | TODO_NOT_CONFIRMED | TODO_SOURCE | Cannot reproduce OmniDreams generation or rollout behavior yet. |
| OmniDreams simulator runtime | TODO_NOT_CONFIRMED | TODO_SOURCE | Cannot run the closed-loop OmniDreams simulator externally yet. |
| AlpaSim orchestrator | TODO_NOT_CONFIRMED | TODO_SOURCE | Cannot reproduce the simulator-state update mechanism yet. |
| Alpamayo 1 policy model | TODO_NOT_CONFIRMED | TODO_SOURCE | Cannot reproduce the paper's closed-loop policy interaction yet. |
| Closed-loop reproduction package | TODO_NOT_CONFIRMED | TODO_SOURCE | Paper-reported closed-loop evaluation remains non-reproducible unless additional artifacts are released. |
| Cosmos foundation platform | Available | https://github.com/NVIDIA/Cosmos | Publicly usable as a foundation/proxy platform for audit workflow smoke tests, but not equivalent to full OmniDreams. |
| Cosmos model collection | Available on Hugging Face | https://huggingface.co/collections/nvidia/cosmos3 | Public model collection exists; access and runtime requirements still need to be checked per model. |
| Cosmos license | Available | https://openmdw.ai/license/1-1/ | Cosmos code and models are released under OpenMDW-1.1; treat this as a model-materials license, not automatically as a conventional permissive OSS license. |
| Cosmos Generator guardrail | Gated dependency noted by Cosmos README | https://github.com/NVIDIA/Cosmos | Generator use may require requesting access to the gated guardrail repository unless guardrails are disabled. |

### Current Interpretation

Cosmos is currently the most relevant public substrate for first-step audit workflow validation because OmniDreams is described as mid- and post-trained from the Cosmos diffusion model, while the full OmniDreams closed-loop autonomous-driving simulator artifacts are not yet confirmed public.

Cosmos-based validation can test the audit workflow and some generative world-model behaviors, such as action-conditioned generation, future-state rollout, temporal drift, and artifact inspection. It cannot validate the full OmniDreams closed-loop AV simulator, because the OmniDreams-specific model, AlpaSim orchestrator, Alpamayo 1 policy integration, simulator-state update mechanism, and closed-loop reproduction package are not confirmed public.

### Audit Rule

Do not treat “paper available” or “Cosmos available” as equivalent to “OmniDreams platform available.” Until OmniDreams-specific runtime artifacts are confirmed, OmniDreams closed-loop results should be recorded as paper-reported evidence rather than independently reproducible evidence.

---

## 0. Audit Summary

### Paper Claim

TODO_SOURCE

### Evidence Provided

TODO_SOURCE

### Audit Judgment

TODO_SOURCE

### Open Questions

- TODO_SOURCE

---

## 1. Basic Pipeline

### Paper Claim

TODO_SOURCE

### Evidence Provided

TODO_SOURCE

### Audit Judgment

TODO_SOURCE

### Open Questions

- TODO_SOURCE

---

## 2. Log-Driven Nature

### Paper Claim

TODO_SOURCE

### Evidence Provided

TODO_SOURCE

### Audit Judgment

TODO_SOURCE

### Open Questions

- TODO_SOURCE

---

## 3. Counterfactual Editing Support

### Paper Claim

TODO_SOURCE

### Evidence Provided

TODO_SOURCE

### Audit Judgment

TODO_SOURCE

### Open Questions

- TODO_SOURCE

---

## 4. Sensor-Level Observation Generation

### Paper Claim

TODO_SOURCE

### Evidence Provided

TODO_SOURCE

### Audit Judgment

TODO_SOURCE

### Open Questions

- TODO_SOURCE

---

## 5. Closed-Loop Rollout Support

### Paper Claim

TODO_SOURCE

### Evidence Provided

TODO_SOURCE

### Audit Judgment

TODO_SOURCE

### Open Questions

- TODO_SOURCE

---

## 6. World State Update Mechanism

### Paper Claim

TODO_SOURCE

### Evidence Provided

TODO_SOURCE

### Audit Judgment

TODO_SOURCE

### Open Questions

- TODO_SOURCE

---

## 7. Supported Sensor-Input E2E Agents

### Paper Claim

TODO_SOURCE

### Evidence Provided

TODO_SOURCE

### Audit Judgment

TODO_SOURCE

### Open Questions

- TODO_SOURCE

---

## 8. Self-Evidence Metrics Used by OmniDreams

### Paper Claim

TODO_SOURCE

### Evidence Provided

TODO_SOURCE

### Audit Judgment

TODO_SOURCE

### Open Questions

- TODO_SOURCE

---

## 9. What These Metrics Actually Prove

### Paper Claim

TODO_SOURCE

### Evidence Provided

TODO_SOURCE

### Audit Judgment

TODO_SOURCE

### Open Questions

- TODO_SOURCE

---

## 10. What These Metrics Do Not Prove

### Paper Claim

TODO_SOURCE

### Evidence Provided

TODO_SOURCE

### Audit Judgment

TODO_SOURCE

### Open Questions

- TODO_SOURCE

---

## 11. Comparison with NeuroNCAP / HUGSIM / UniSim / AdvSim

### Paper Claim

TODO_SOURCE

### Evidence Provided

TODO_SOURCE

### Audit Judgment

TODO_SOURCE

### Open Questions

- TODO_SOURCE

---

## 12. Missing Credibility Evidence

Focus on task-relevant relational consistency rather than photorealism alone.

### Candidate Missing Evidence

- front / rear / left / right stability
- same-lane / adjacent-lane / off-road consistency
- approaching / receding consistency
- occluding / occluded-by consistency
- risk-increasing / risk-decreasing evidence
- whether collision / near-miss is a real model failure or simulation artifact
- whether high-risk relations are supported by sensor, geometry, map, and temporal evidence

### Paper Claim

TODO_SOURCE

### Evidence Provided

TODO_SOURCE

### Audit Judgment

TODO_SOURCE

### Open Questions

- TODO_SOURCE

---

## 13. Preliminary Judgment

TODO_SOURCE