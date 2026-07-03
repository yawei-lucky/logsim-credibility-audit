# Log-Driven Counterfactual Closed-Loop Simulation Credibility Audit

本项目研究真实驾驶日志驱动、可反事实修改、传感器级输入、闭环交互的自动驾驶仿真器，其核心问题是：这类仿真器生成的闭环测试结果是否可信，是否足以支撑端到端自动驾驶模型的评估结论。

## 当前研究主线

当前第一阶段聚焦：

**HUGSIM 这一类真实日志重建型闭环仿真器**

原因是 HUGSIM 更接近当前可运行、可审计的 3DGS-based closed-loop simulation 路线，适合作为第一阶段对象，优先分析它如何完成：

- 真实日志场景重建；
- 3D Gaussian Splatting 表示；
- 反事实场景修改；
- 传感器级观测生成；
- agent 行为闭环反馈；
- ego / actor 状态更新；
- 连续 rollout；
- 自动驾驶模型评估。

OmniDreams / Cosmos 方向暂时后移，作为未来生成式世界模型闭环仿真的对照与扩展方向。

## 对照对象

以下工作作为历史脉络和横向对照：

- NeuroNCAP
- HUGSIM
- UniSim
- AdvSim
- OmniDreams

这些工作用于回答：

- 早期真实日志驱动闭环仿真如何自证可信；
- 它们使用了哪些指标；
- 这些指标证明了什么；
- 这些指标没有证明什么；
- HUGSIM / OmniDreams 相比它们是否解决了旧问题，还是只是换了一种场景表示方式。

## 核心研究问题

RQ1. HUGSIM 这一类仿真器如何证明自己的仿真结果可信？

RQ2. 它的指标是在验证仿真器可信性，还是只是在验证模型表现？

RQ3. 它是否能发现低可信反事实样本、重建 artifact、遮挡错误、深度错误和关系不一致？

RQ4. NeuroNCAP / UniSim / AdvSim / OmniDreams 中已有的自证指标，能否用于审计 HUGSIM？

RQ5. 是否仍然需要一个 credibility audit layer，用来判断闭环测试证据应被 accepted、down-weighted，还是 rejected？

## 当前工作原则

本阶段不急于提出新 verifier，也不急于复现所有系统。

第一步只做一件事：

**审计 HUGSIM 这一类真实日志重建型闭环仿真器的自证机制。**

然后再用 NeuroNCAP / UniSim / AdvSim / OmniDreams 作为对照，判断 HUGSIM 是否真正推进了日志驱动反事实闭环仿真的可信评估问题。

## 文件结构

核心文件：

- `README.md`
- `PROJECT_STATE.md`
- `SOURCE_AVAILABILITY_GATE.md`
- `docs/hugsim_audit.md`
- `docs/runnable_target_selection.md`
- `docs/hugsim_smoke_test_plan.md`
- `docs/comparison_notes.md`

辅助文件：

- `docs/literature_matrix.md`
- `docs/codex_workflow.md`
- `docs/future/omnidreams_audit.md`

其中 `docs/hugsim_audit.md` 是第一阶段优先文件。
