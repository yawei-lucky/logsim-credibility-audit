# Research Guiding Principles

> Status: durable research direction. These principles guide experiments but
> do not yet define the final credibility metric.

## Core Question

> HUGSIM 提供给智驾系统的任务相关信息，是否与现实一致到足以产生可信的感知、决策和闭环结果？

The target is not visual realism by itself. The target is whether a simulator
preserves the information, causal relations, and closed-loop consequences that
matter to a receiver performing a driving task.

## Comparative Validation Guideline

> 同一个智驾模型面对现实数据和对应的仿真数据，是否形成相近的感知、风险排序、规划和控制行为？

This matched real-versus-sim comparison is the strongest direct-comparison
guide for developing credibility evidence. Agreement should be evaluated at
task-relevant levels, not only through pixel similarity:

- perception and scene understanding;
- hazard recognition and risk ordering;
- planning and control response;
- closed-loop safety and task outcomes.

Matching outputs do not make simulation literally identical to reality. They
provide bounded evidence that the simulation is fit for a specified driving
task, receiver, ODD, and intervention range.

### Target receiver versus validation instrument

The same AD model may play two roles that must not be conflated:

1. **Target AD / system under test.** Ask whether the fixed model receives
   sufficiently equivalent task information and exposes comparable behavior
   in real and simulated factual inputs. The model need not be perfect for this
   receiver-specific comparison.
2. **Validation instrument.** Use the model's outputs to assert that simulator
   geometry, planning quality or risk is correct. This stronger role requires
   a local real-data qualification, an error envelope and evidence that the
   result is not an adapter or receiver failure.

A real-data receiver qualification does not prove the AD is globally correct
or safe. It checks the local input contract, non-degenerate operation,
repeatability, sensitivity to known corruptions, and task error over a declared
real-data slice.

For matched factual and designed-counterfactual work, keep two differences
separate:

```text
D_domain = target-AD difference between matched real and factual simulation
E_CF     = target-AD change from simulated factual to counterfactual input
```

Counterfactual evidence is stronger when `E_CF` preserves the preregistered
direction and remains distinguishable from factual domain discrepancy,
receiver error, repeat sensitivity and reasonable perturbations. This does
not make a nonexistent counterfactual future a measured real-world truth.

## Reality Grounding Without Requiring a Real Starting Scene

A designed counterfactual does **not** require every test case to begin from a
matched real-log scene. Requiring an exact real counterpart for every case
would prevent simulation from testing rare, unsafe, or deliberately novel
conditions—the main reason to use counterfactual simulation.

Distinguish two levels of grounding:

1. **Scenario-level factual anchoring** is a strong evidence path, but it is
   optional for an individual designed counterfactual.
2. **Framework- and instrument-level external validity** is required before an
   indicator can support a real-world-equivalence claim. The metric, receiver,
   physical constraint, or behavioral model must be qualified somewhere
   against evidence that is not produced solely by the simulator under test.

External qualification may use matched real observations, independent manual
or sensor measurements, controlled-track experiments, physical laws,
empirical behavior distributions, or receiver behavior already characterized
on real data. It need not always use an exact log match, but it must provide a
traceable source of real-world validity.

> 可信反事实不要求每个场景都有匹配现实起点；但用于判断它的指标、约束和接收方，必须通过独立现实证据或可检验规律获得资格。

An indicator is not self-validating. Calling it "strong" requires evidence
that it measures the intended construct, separates known conforming and
nonconforming cases, is calibrated to a task or decision consequence,
generalizes over its declared range, and does not use HUGSIM outputs as the
sole reference for judging those same outputs.

### Two-level validation logic

**Level 1 — qualify the validation instruments.** Establish the applicability,
error envelope, independence, and failure modes of each metric, receiver,
constraint, and reference using external evidence where appropriate.

**Level 2 — evaluate designed counterfactuals.** A counterfactual without an
exact real counterpart may then be assessed through:

- physical, geometric, visibility, and causal constraints;
- consistency across qualified receivers with materially different failure
  modes;
- sensitivity to plausible vehicle behavior, rendering, dynamics, and
  receiver uncertainty;
- stability of task relations, critical-object ordering, decisions, and
  outcomes across that uncertainty range.

Such evidence can support physical admissibility, causal consistency,
model-robust task behavior, and bounded fitness for stress testing. It cannot
establish that one exact unobserved future is the unique real outcome. A
matched factual comparison remains the strongest direct upgrade for
real–simulation equivalence, not a universal prerequisite for running or
learning from a counterfactual experiment.

Multiple receivers are also not automatically independent. Versions from the
same model family or models trained on the same data may share failure modes;
their agreement must be weighted by evidence dependence rather than counted as
simple votes.

## Receiver: Automated Driving and Human-in-the-Loop

The receiver can be:

- an automated-driving model or complete AD stack;
- a human driver operating in a human-in-the-loop simulator;
- both, when complementary evidence is needed.

Human-in-the-loop evaluation asks whether matched real and simulated driving
conditions produce statistically consistent hazard recognition, intervention
timing, control behavior, task performance, and safety outcomes. Subjective
realism ratings can be recorded, but they are supporting evidence rather than
the sole credibility criterion.

Human performance cannot automatically substitute for AD-model validation:
humans and machine receivers may depend on different visual cues. A simulator
intended as an AD testing domain should therefore be validated with the target
receiver class, while human-in-the-loop evidence provides an additional
behavioral and experiential anchor.

### Receiver Convergence Principle

> 不要求人类驾驶员与 AD 模型依赖完全相同的内部视觉线索；通过共享任务情境和共同任务变量，分别验证各接收方内部的真实—仿真一致性；跨接收方只检查各自的真实—仿真差值及干预效应方向是否收敛，不要求人与 AD 的原始输出一致。

A six-camera surround view can make scene coverage, ego reference, and event
timing more comparable, but it does not make human and machine perception
equivalent. For an initial controlled human study, compose a fixed human
display from the same synchronized per-camera source frames supplied to the AD
receiver, preserving field of view, resolution, timing, and latency. The AD
still consumes its native tensor/interface rather than a human-facing video
mosaic. Treat a natural cockpit, mirrors, head motion, and motion feedback as
a different receiver domain.

Validation is performed within each receiver first:

```text
same AD version: real vs simulated observations
same human where possible, or a matched participant population: real vs simulated condition
```

Across receiver types, compare real-to-simulation gaps and intervention-effect
directions on shared external task variables such as critical-object
detection, risk ordering, lane relation, visibility, intervention timing,
response direction, and safety outcome. Do not require human scores, AD
scores, internal features, or exact trajectories to be numerically identical.

A within-participant human comparison is preferred. If matched groups are
used, record the weaker pairing and account for participant and presentation-
order effects.

## What Kind of Realism Matters

Visible animation, texture, or lighting differences are not automatically
fatal. They matter when they change task-relevant information or receiver
behavior. Conversely, photorealistic output is not sufficient when geometry,
depth, occlusion, motion, semantics, causality, or safety outcomes disagree
with reality.

The research therefore prioritizes:

1. task-relevant information consistency;
2. causal consistency under controlled interventions;
3. receiver-behavior consistency;
4. closed-loop outcome consistency;
5. explicit applicability and failure boundaries.

## Role of HUGSIM Experiments

HUGSIM is the first experimental object, not the result to be proved and not
the final framework. Its positive results, negative results, capability
boundaries, and unresolved areas are experimental material for developing a
general method that determines whether a world simulator is fit to serve as
an intelligent-driving test domain.

Small implementation defects remain in run-level technical records when they
affect reproducibility or invalidate a result. They are not promoted to core
theoretical findings unless repeated evidence shows a general credibility
mechanism.

## Intended Research Progression

The progression has two evidence paths rather than one mandatory linear chain:

```text
instrument / framework qualification
  -> independent reality evidence, physical laws, controlled measurements
  -> qualified metrics, receivers, constraints, and uncertainty ranges

case-level evaluation
  -> matched factual real/sim path, when available
  OR
  -> designed counterfactual path without an exact real counterpart
       -> causal constraints + receiver convergence + sensitivity analysis

both paths
  -> behavior and outcome comparison
  -> positive evidence, negative evidence, and applicability boundaries
  -> credibility-validation framework and metrics
```

The future four-layer evidence chain is therefore an organizational structure,
not a serial self-proof. Each layer should form an evidence network with
independence, external validity, causal constraints, and downstream
consequences made explicit.

The eventual output should be a unified validation protocol for
fitness-for-use. It may combine mandatory validity gates, dimension-specific
evidence, uncertainty, and an applicability statement rather than collapsing
all credibility into one visual-quality score.
