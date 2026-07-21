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

This matched real-versus-sim comparison is the primary guide for developing
credibility evidence. Agreement should be evaluated at task-relevant levels,
not only through pixel similarity:

- perception and scene understanding;
- hazard recognition and risk ordering;
- planning and control response;
- closed-loop safety and task outcomes.

Matching outputs do not make simulation literally identical to reality. They
provide bounded evidence that the simulation is fit for a specified driving
task, receiver, ODD, and intervention range.

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

```text
real-log anchor
-> matched real/sim observations
-> matched automated or human receiver
-> controlled counterfactual intervention
-> behavior and outcome comparison
-> positive evidence, negative evidence, and applicability boundaries
-> credibility-validation framework and metrics
```

The eventual output should be a unified validation protocol for
fitness-for-use. It may combine mandatory validity gates, dimension-specific
evidence, uncertainty, and an applicability statement rather than collapsing
all credibility into one visual-quality score.
