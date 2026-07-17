# Log-Driven Counterfactual Closed-Loop Simulation Credibility Audit

本项目研究 **日志驱动、可反事实修改、传感器级输入、闭环交互** 的自动驾驶仿真器可信性问题。

总目标不是复现某篇论文的分数，也不是判断生成画面是否足够逼真，而是建立一套用于审计闭环仿真证据的研究方法：

> 仿真器生成的闭环测试结果，是否足以作为评估端到端自动驾驶模型的可信证据？

## 当前阶段目的

当前阶段使用 **HUGSIM** 作为实验载体，搭建一条最小闭环证据链，用于发展后续的可信验证方法和指标。

当前 HUGSIM 实验的目的不是证明 HUGSIM 本身可信，也不是复现完整 benchmark，而是完成：

> HUGSIM closed-loop evidence pipeline smoke test

也就是验证我们能否从一个真实闭环仿真器中稳定收集以下证据：

```text
scenario / scene source
→ sensor-level observation
→ agent or dummy planner output
→ control action
→ ego / actor state update
→ closed-loop rollout
→ metric event
→ credibility judgment basis
```

## 当前实验对象

当前选择 HUGSIM，是因为它具备第一阶段所需的关键条件：

- 真实日志 / 数据集驱动；
- 3DGS 场景重建；
- 传感器级观测生成；
- 支持闭环 rollout；
- 有公开代码和运行入口；
- 适合搭建最小可信审计流程。

OmniDreams / Cosmos 暂时后移，作为未来生成式世界模型闭环仿真的对照与扩展方向。

## 当前方法路线

当前采用四步路线：

1. **Source Availability Gate**  
   先判断论文、代码、模型、数据、runtime、评估脚本是否公开可查。

2. **Closed-loop Evidence Completeness**  
   判断一次闭环仿真是否产生了完整证据链，包括 observation、planner output、action、ego / actor state update、metrics 和输出文件。

3. **Segment-level Evidence Judgment**  
   对单个 closed-loop segment 做 evidence qualification：
   - accepted
   - down-weighted
   - rejected

4. **Future Credibility Metric**  
   在积累多个 run 和多个 segment 后，再定义量化的 simulator credibility metric。

这里的 accepted / down-weighted / rejected 是当前阶段的证据处理方式，不是项目总目标，也不是最终数值指标。

## 当前状态

已经完成：

- HUGSIM source availability gate；
- HUGSIM pipeline / closed-loop mechanism 抽取；
- HUGSIM smoke-test 设计；
- deterministic plan-pipe writer；
- accepted / down-weighted / rejected 判定规则；
- CUDA / pixi 环境问题排查和 runbook；
- 第一份 HUGSIM smoke-test run report；
- 第一份 run report 的 Research Commander review；
- HUGSIM 本地 clone 与 PyTorch cu121 / CUDA 12.1 环境验证；
- 公开 `scene-0383` 资产下载、校验与本地配置；
- bounded debug runner；
- 3-step deterministic closed-loop smoke test；
- 第一条真实 segment-level credibility audit record。

第一份运行是环境 bring-up，没有产生闭环证据。第二份运行已经完整进入：

```text
env.reset
→ obs_pipe
→ plan_pipe
→ env.step
→ output files
→ credibility judgment: down-weighted
```

第一条闭环证据标为 `down-weighted`：最小闭环链路、状态更新和评分代码均已跑通，但片段仅 0.75 秒、无动态 actor，侧向视角存在可见模糊/拖影，且尚未完成 RGB / semantic / depth 像素级一致性检查。

## 当前重点

下一步不扩大文献范围，也不运行完整 HUGSIM benchmark，而是提高已跑通证据链的质量：

```text
RGB / semantic / depth synchronized evidence
→ cross-modal consistency checks
→ longer bounded normal segment
→ state / rendering / metric stability
→ stronger accepted or updated down-weighted record
```

## 暂缓内容

当前暂缓：

- OmniDreams / Cosmos 大模型世界仿真；
- 完整 HUGSIM benchmark 复现；
- UniAD / VAD / LTF 全模型评测；
- 新 verifier 的完整设计；
- 大规模量化 credibility metric。

## 文件结构

核心文件：

- `README.md`
- `PROJECT_STATE.md`
- `SOURCE_AVAILABILITY_GATE.md`
- `docs/hugsim_audit.md`
- `docs/hugsim_smoke_test_plan.md`
- `docs/hugsim_credibility_decision_rules.md`
- `docs/hugsim_cuda_pixi_runbook.md`
- `docs/runs/hugsim_smoke_test_001.md`
- `docs/runs/hugsim_smoke_test_001_review.md`
- `docs/runs/hugsim_smoke_test_002.md`
- `docs/runs/hugsim_smoke_test_002_audit.json`

辅助文件：

- `docs/runnable_target_selection.md`
- `docs/comparison_notes.md`
- `docs/literature_matrix.md`
- `docs/codex_workflow.md`
- `docs/future/omnidreams_audit.md`
- `scripts/check_hugsim_smoke_prereqs.py`
- `scripts/hugsim_plan_pipe_writer.py`
- `scripts/run_hugsim_debug_smoke.py`
- `configs/hugsim/nuscenes_smoke_base.yaml`

## 项目判断

HUGSIM 是当前实验载体；真正目标是形成 **closed-loop simulation credibility audit methodology**。

当前阶段的关键问题是：

> 一次闭环仿真结果在什么证据条件下可以被 accepted，什么时候应该 down-weighted，什么时候必须 rejected？
