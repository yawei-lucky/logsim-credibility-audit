# HUGSIM first-stage credibility evidence closure 001

Date: 2026-07-25

## Research conclusion form

The project does not seek an unconditional HUGSIM credibility score. Its
eventual conclusion must state:

> credible for which task, scenario range, receiver, intervention type and
> error boundary.

Visual realism, HUGSIM-native semantic/depth/score outputs, and one plausible
AD trajectory cannot independently establish credibility. The required object
is an evidence network connecting intervention validity, sensor information,
AD domain difference, counterfactual response, uncertainty sensitivity and
downstream consequences.

## Stage-closing decision

HUGSIM is `accepted` as a first-stage experimental carrier: the pinned local
system can reconstruct a real-log scene, render six-camera RGB, add controlled
counterfactual actors, pass those images through a fixed target AD and close a
bounded plan-to-simulator loop.

HUGSIM as a generally credible AD world simulator remains `rejected` at that
claim scope because the available work does not test or qualify that global
claim. This is a scope boundary, not a claim that HUGSIM has globally failed.

The accumulated evidence bundle is overall `down-weighted`: it contains useful
positive directions, isolated negative findings and explicit capability
boundaries, but lacks sufficient source-independent sensor, behavior and
real-world outcome references.

## Positive evidence retained

| Evidence | Decision | Strongest supported statement |
|---|---|---|
| controlled geometry, motion, visibility and interaction pilots | `accepted` | selected simulator-internal hard relations and obvious endpoint directions can be exercised and audited |
| Sparse4Dv3 supporting receiver gate | `accepted` | bounded vehicle-presence and ordinal relation probing; not absolute 3D truth |
| SparseDrive real-source runtime/reset/input-sensitivity gate | `accepted` | the pinned adapter can use the selected real six-camera slice as a target AD |
| SparseDrive visual-necessity control | `accepted` | complete RGB removal materially changes the plan; correct visual semantics remain unqualified |
| CF-R plan-direction experiment | `accepted` | in its fixed-mode designed range, stronger closure produced ordered native planning responses |
| plan-to-loop and live-feedback interface gates | `accepted` | new six-camera observations reach SparseDrive and fresh plans reach the HUGSIM loop |
| replicated CF-R closed-loop condition effect | `accepted` | the simulator-internal condition effect exceeded same-condition repeat sensitivity for the audited constructs |
| official sample matched-pose comparison | `down-weighted` | a partial factual image anchor exists; exact release pairing and task equivalence remain unresolved |
| matched factual SparseDrive pilot | `down-weighted` | one five-frame window measured a factual real–sim receiver-domain discrepancy |
| same-window candidate-mode decomposition | `down-weighted` | candidate response, mode selection and repeat/domain diagnostics can be separated for one target AD |

## Negative evidence retained

| Finding or claim | Decision | Why it matters |
|---|---|---|
| rollout-tail NC/TTC claims based on repeated final actor boxes | `rejected` | missing future actor state can manufacture a risk event |
| exact numerical closed-loop reset reproducibility | `rejected` | action direction remained stable, but plan differences accumulated beyond the exact-repeat claim |
| projected metadata box / centre-only Gaussian as precise RGB support truth | `rejected` | simulator-declared geometry did not qualify precise rendered pixel support |
| unconditional strong-actor-less-forward endpoint rule | `rejected` | it held at only `3/5` same-window timestamps |
| route endpoint as a maneuver-independent risk metric | `rejected` | frame `48` reverses only after a native mode-selection change |
| current-static actor clearance as dynamic risk | `rejected` | it lacks time-aligned future actor motion and saturates at zero in `4/5` strong frames |
| plausible SparseDrive trajectory as proof of semantic correctness | `rejected` | plausible output can remain after severe visual controls |
| any current result as proof of HUGSIM safety or global credibility | `rejected` | scope exceeds the evidence network |

Negative results are retained as method evidence. They are not rewritten after
the fact and do not make the experiments useless.

## Current metric/tool qualification

| Tool | Current status | Allowed use |
|---|---|---|
| intervention/state hard gates | `accepted` | verify that the declared experimental change occurred internally |
| independent recomputation from HUGSIM-declared states | `down-weighted` | detect scorer/implementation inconsistency; not real-world truth |
| fixed Sparse4Dv3 ordinal response | `down-weighted` | supporting relation probe in its qualified range |
| SparseDrive native candidate/score decomposition | `accepted` | diagnose mode-selection versus fixed-mode response |
| route-relative progress | `down-weighted` | compare explicit comparable maneuver branches only |
| observed repeat envelope | `accepted` | local numerical-sensitivity reference for the same pipeline |
| one-slice factual real–sim AD difference | `down-weighted` | empirical domain scale, not a universal acceptance threshold |
| static current-actor plan clearance | `rejected` | visualization only; not dynamic risk |
| HUGSIM native TTC/PDMS/HDScore | `down-weighted` | AD performance under HUGSIM after validity checks; not simulator credibility |

No current tool is qualified as a standalone real-world risk judge.

## Capability boundary and unresolved evidence

Current evidence does not establish:

- source-independent six-camera sensor equivalence over multiple conditions;
- independent 3D geometry, motion and occlusion accuracy;
- calibrated SparseDrive risk or planning correctness;
- receiver-independence across heterogeneous AD architectures;
- realistic response magnitude for scripted actors;
- real traffic interaction, physical TTC or collision validity;
- correspondence between HUGSIM closed-loop outcomes and real driving
  consequences;
- safety of an AD that does not fail in the tested simulations.

The current strongest bounded conclusion is:

> In the audited daytime urban source slice and designed interventions, the
> pinned HUGSIM/SparseDrive pipeline can produce reproducible, decomposable
> task-level and closed-loop responses whose direction is informative in some
> explicitly stated constructs. Several seemingly reasonable risk indicators
> fail under mode changes or temporal misalignment. Real-world fitness remains
> unqualified.

## Next stage

Stop tuning the current five-frame result. The next evidence upgrade is
external validity, kept minimal:

1. add a small number of high-value matched real–sim slices with the same
   six-camera/pose/time contract;
2. obtain an independent reference only for the task variables needed by the
   intended claim, such as actor geometry, visibility or recorded ego response;
3. define real–sim AD response differences and acceptance bounds before
   interpreting new counterfactuals;
4. when dynamic path conflict is used, require complete time-aligned future
   actor states, ego footprint and valid-horizon coverage;
5. add a second heterogeneous AD receiver only if the key result is shown to
   depend materially on SparseDrive.

The eventual research framework can organize these results under log
reproduction, sensor consistency, task-level consistency and closed-loop
outcome credibility. These four layers remain a future evidence-chain
structure, not current HUGSIM stage scores.

## Primary supporting records

- `docs/runs/counterfactual_indicator_phase_001_closure.md`;
- `docs/runs/hugsim_supporting_receiver_qualification_001.md`;
- `docs/runs/hugsim_cf_r_plan_001.md`;
- `docs/runs/hugsim_sparsedrive_plan_to_loop_001.md`;
- `docs/runs/hugsim_sparsedrive_live_loop_001.md`;
- `docs/runs/hugsim_cf_r_closed_loop_001.md`;
- `docs/runs/hugsim_official_sample_matched_pose_001.md`;
- `docs/runs/sparsedrive_real_source_qualification_001.md`;
- `docs/runs/sparsedrive_visual_necessity_002.md`;
- `docs/runs/sparsedrive_real_sim_factual_001.md`;
- `docs/runs/sparsedrive_same_window_counterfactual_001.md`;
- `docs/runs/sparsedrive_maneuver_conditioned_risk_001.md`.
