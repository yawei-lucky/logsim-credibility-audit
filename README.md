# Log-Driven Counterfactual Closed-Loop Simulation Credibility Audit

本项目研究真实驾驶日志驱动、可反事实修改、传感器级输入、闭环交互的自动驾驶仿真器，其核心问题是：这类仿真器生成的闭环测试结果是否可信，是否足以支撑端到端自动驾驶模型的评估结论。

## 当前研究主线

当前第一审计对象调整为：

**OmniDreams**

原因是 OmniDreams 更接近最新一代生成式闭环仿真 / 世界模型仿真方向，适合作为主线对象，优先分析它如何完成：

- 真实场景建模；
- 反事实场景修改；
- 传感器级观测生成；
- agent 行为闭环反馈；
- 连续 rollout；
- 端到端自动驾驶模型评估。

## 对照对象

以下工作作为历史脉络和横向对照：

- NeuroNCAP
- HUGSIM
- UniSim
- AdvSim

这些工作用于回答：

- 早期真实日志驱动闭环仿真如何自证可信；
- 它们使用了哪些指标；
- 这些指标证明了什么；
- 这些指标没有证明什么；
- OmniDreams 相比它们是否解决了旧问题，还是只是换了一种生成方式。

## 核心研究问题

RQ1. OmniDreams 如何证明自己的仿真结果可信？

RQ2. 它的指标是在验证仿真器可信性，还是只是在验证模型表现？

RQ3. 它是否能发现低可信反事实样本、生成 artifact、遮挡错误、深度错误和关系不一致？

RQ4. NeuroNCAP / HUGSIM / UniSim / AdvSim 中已有的自证指标，能否用于审计 OmniDreams？

RQ5. 是否仍然需要一个 credibility audit layer，用来判断闭环测试证据应被 accepted、down-weighted，还是 rejected？

## 当前工作原则

本阶段不急于提出新 verifier，也不急于复现所有系统。

第一步只做一件事：

**审计 OmniDreams 的自证机制。**

然后再用 NeuroNCAP / HUGSIM / UniSim / AdvSim 作为对照，判断 OmniDreams 是否真正推进了日志驱动反事实闭环仿真的可信评估问题。

## 文件结构

核心文件：

- `README.md`
- `PROJECT_STATE.md`
- `docs/omnidreams_audit.md`
- `docs/comparison_notes.md`

辅助文件：

- `docs/literature_matrix.md`
- `docs/codex_workflow.md`

其中 `docs/omnidreams_audit.md` 是第一优先级。
