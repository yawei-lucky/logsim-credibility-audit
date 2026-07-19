# Log-Driven Counterfactual Closed-Loop Simulation Credibility Audit

本项目研究 **日志驱动、可反事实修改、传感器级输入、闭环交互** 的自动驾驶仿真器可信性问题。

总目标不是复现某篇论文的分数，也不是判断生成画面是否足够逼真，而是建立一套用于审计闭环仿真证据的研究方法：

> 仿真器生成的闭环测试结果，是否足以作为评估端到端自动驾驶模型的可信证据？

## 日志驱动定义

本项目采用广义定义：

> 日志驱动仿真器以真实道路采集序列为基础，重建或构造可交互环境，并在其上生成反事实闭环过程；不要求简单回放原始日志。

因此 HUGSIM 属于研究范围，更准确地说是**基于真实驾驶数据序列重建、支持反事实编辑的闭环神经仿真器**。真实数据来源不意味着新视角、插入车辆和未来交互天然可信，这正是本项目要验证的问题。

## 当前阶段目的

当前阶段使用 **HUGSIM** 作为实验载体。最小闭环证据链已经跑通，当前工作已进入严格配对的 relation-level counterfactual audit。

当前 HUGSIM 实验的目的不是证明 HUGSIM 本身可信，也不是复现完整 benchmark，而是完成：

> HUGSIM relation-level counterfactual credibility audit

也就是检验风险事件是否能被传感器、状态、几何、时序和负对照共同归因：

```text
scenario / scene source
→ sensor-level observation
→ agent or dummy planner output
→ control action
→ ego / actor state update
→ closed-loop rollout
→ metric event
→ paired counterfactual / negative control
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

## 当前工作流程

当前采用四步测试与证据处理路线：

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

长期的可信评价指标计划沿四层证据链研究：**日志复现、传感器一致性、任务级一致性、闭环结果可信性**。这四层是未来指标的证据组织思路，不是当前实验阶段，也不用于现在给 HUGSIM 逐层打分。当前仍先完成测试、对照、证据积累和因果归因。

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
- 第一条真实 segment-level credibility audit record；
- released `traj2control` 坐标/航向不一致的控制混杂定位；
- corrected control adapter 与 4 个回归测试；
- 无车、同车道静止车辆、相邻车道静止车辆三组严格配对的 5 秒实验；
- RGB / semantic / depth 像素级反事实证据和可视化；
- 第一条经过第三方复核的 relation-level `down-weighted` audit record，并保留内部几何子结论为 `accepted`。
- 6 秒/24 步的多车强干预实验：一辆前方慢车和一辆右侧斜向切入车；
- 多车前视对比视频、五时刻跨模态图、俯视轨迹和风险时间线；
- 第一条 multi-actor `down-weighted` audit record，并保留严格配对、多实例渲染和内部风险时序子结论为 `accepted`。

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

最新的三组 counterfactual 实验保持 ego state 和 action 完全相同：

| 条件 | NC | TTC | PDMS | HDScore |
|---|---:|---:|---:|---:|
| 无车辆 | 1.000 | 1.000 | 1.000 | 0.150 |
| 横向0.0米车辆 | 0.700 | 0.500 | 0.557 | 0.084 |
| 横向3.5米车辆 | 1.000 | 1.000 | 1.000 | 0.150 |

三组内部状态和控制严格配对；横向0.0米和3.5米位置产生不同内部 TTC/NC 响应。该子结论为 `accepted`。但车辆与背景存在可见视觉域差异，跨模态输出来自同一渲染器，也没有真实日志参考帧或 sensor-input AD agent，因此完整片段为 `down-weighted`。

最新多车强干预实验同样保持 ego state 和 action 完全一致。右侧切入车约在 5.0 秒穿过 ego 中心线附近，TTC 从 4.75 秒失败，NC 从 5.75 秒失败；多车组 PDMS 为 0.798，而配对无车组为 1.0。实际 runtime collision 仍为 false。该结果支持多实例渲染、actor state evolution 和内部规划路径风险响应，不支持真实碰撞或 AD agent 响应。

## 当前重点

当前优先审阅明显强干预的多车汇入结果，而不是继续做微小位置变化：

```text
no-actor baseline
→ lead vehicle + right-side cut-in
→ synchronized RGB / semantic / depth and actor trajectories
→ TTC / NC event timing
→ claim-specific credibility judgment
```

如果继续多车测试，下一次应使用不同车辆资产和更可信的地图约束汇入轨迹。真实源日志锚点仍是后续验证传感器真实性的重要任务，但不是本轮强干预实验的即时动作。

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
- `docs/runs/hugsim_counterfactual_001.md`
- `docs/runs/hugsim_counterfactual_001_audit.json`
- `docs/runs/hugsim_multicar_cut_in_001.md`
- `docs/runs/hugsim_multicar_cut_in_001_audit.json`
- `CODEX_NEXT_TASK.md`

辅助文件：

- `docs/runnable_target_selection.md`
- `docs/comparison_notes.md`
- `docs/literature_matrix.md`
- `docs/codex_workflow.md`
- `docs/future/omnidreams_audit.md`
- `scripts/check_hugsim_smoke_prereqs.py`
- `scripts/hugsim_plan_pipe_writer.py`
- `scripts/run_hugsim_debug_smoke.py`
- `scripts/hugsim_control_adapter.py`
- `scripts/analyze_hugsim_counterfactual.py`
- `scripts/analyze_hugsim_multicar.py`
- `configs/hugsim/nuscenes_smoke_base.yaml`
- `configs/hugsim/scenarios/scene-0383-adjacent-static-00.yaml`
- `configs/hugsim/scenarios/scene-0383-multicar-cut-in-00.yaml`

## 项目判断

HUGSIM 是当前实验载体；真正目标是形成 **closed-loop simulation credibility audit methodology**。

当前阶段的关键问题是：

> 一次闭环仿真结果在什么证据条件下可以被 accepted，什么时候应该 down-weighted，什么时候必须 rejected？
