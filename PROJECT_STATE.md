# Research Commander — LogSim Credibility Audit 状态总结

## 1. 项目定位

本项目研究 **日志驱动型反事实闭环仿真可信验证**。

研究对象不是普通 open-loop planning benchmark，也不是 motion-only simulation 或纯 CARLA 合成仿真，而是：

真实驾驶日志  
→ 可反事实修改  
→ 传感器级观测生成  
→ sensor-input E2E agent / 自动驾驶模型  
→ 输出轨迹或控制  
→ 闭环状态更新  
→ 连续 rollout  
→ 评估自动驾驶系统表现

核心问题不是“仿真器能不能生成好看的图像”，而是：

> 这些仿真器生成的闭环测试结果是否可信，是否足以支撑端到端自动驾驶模型的评估结论？

本项目中的“日志驱动”采用广义定义：

> 以真实道路采集序列为基础，重建或构造可交互环境，并在其上生成反事实闭环过程；不要求简单回放原始日志。

据此，HUGSIM 是基于真实驾驶数据序列重建、支持反事实编辑的闭环神经仿真器，属于当前研究范围。

---

## 2. 当前阶段定位

当前第一阶段审计对象是：

**HUGSIM 这一类真实日志重建型闭环仿真器**

HUGSIM 是当前实验载体，不是本项目的最终目标。

当前阶段已经用 HUGSIM 搭建并验证了最小闭环证据链，正在用严格配对的反事实实验发展闭环仿真可信验证方法。

当前 HUGSIM 实验的定位是：

> HUGSIM relation-level counterfactual credibility audit

也就是说，当前实验不是为了证明 HUGSIM 本身可信，也不是为了复现完整 benchmark，而是检验风险事件是否能被传感器、状态、几何、时间和负对照共同归因：

```text
scenario / scene source
→ sensor-level observation
→ planner output
→ control action
→ ego / actor state update
→ closed-loop rollout
→ metric event
→ paired counterfactual / negative control
→ credibility judgment basis
```

OmniDreams / Cosmos 暂时后移，作为未来生成式世界模型闭环仿真的对照与扩展方向。

---

## 3. 四层可信证据链

本项目的方法主线是四层逐层支撑的可信证据链：

### 第一层 — 日志复现

验证仿真场景能否追溯并复现真实采集日志中的场景、位姿、观测和动态事实。

### 第二层 — 传感器一致性

验证生成的 RGB、语义、深度、多相机和时序观测是否与真实传感器证据及彼此一致。

### 第三层 — 任务级一致性

验证车道、可行驶区域、相对位置、遮挡、接近、碰撞和 TTC 等任务关系在受控反事实下是否一致。

### 第四层 — 闭环结果可信性

验证 observation、decision、action、state update 和 outcome 构成的闭环结果能否作为评价自动驾驶系统的可信证据。

Source Availability Gate 是外部审计的前置门槛；Closed-loop Evidence Completeness 是证据记录完整性检查；`accepted`、`down-weighted`、`rejected` 是针对具体证据主张的判定标签。它们都不是四层本身。

---

## 4. 主线研究问题

### RQ1

HUGSIM 如何证明自己的仿真结果可信？

### RQ2

HUGSIM 的指标是在验证仿真器可信性，还是只是在验证自动驾驶模型表现？

### RQ3

HUGSIM 是否能发现低可信反事实样本、3DGS 重建 artifact、遮挡错误、深度错误、几何关系不一致、时序关系不一致？

### RQ4

NeuroNCAP / UniSim / AdvSim / OmniDreams 的自证指标，能否迁移到 HUGSIM 上？

### RQ5

是否仍然需要一个 credibility audit layer，用来判断闭环测试证据应被 accepted、down-weighted、rejected？

---

## 5. 当前理论判断

真实日志驱动反事实闭环仿真是必要方向，但它不是天然可信。

端到端自动驾驶 / sensor-input E2E agent 的趋势使评估问题从 motion-level planning 推进到 sensor-to-action closed-loop evaluation。

3DGS-based reconstruction simulator 比 NeRF-based simulator 更接近当前实时可运行路线，但实时渲染和视觉逼真度不等于可信闭环评估。

因此，本项目的关键判断是：

> sensor-level closed-loop evaluation 变得不可回避；  
> counterfactual simulation 使 credibility audit 变得不可回避；  
> 3DGS / NeRF / world model 都必须接受 source availability 与 relation-level consistency 审计。

---

## 6. 当前已完成事项

已完成：

- HUGSIM Source Availability Gate；
- HUGSIM pipeline / closed-loop mechanism 第一轮抽取；
- HUGSIM smoke-test plan；
- HUGSIM accepted / down-weighted / rejected 证据规则；
- 本地预检脚本 `scripts/check_hugsim_smoke_prereqs.py`；
- deterministic plan-pipe writer `scripts/hugsim_plan_pipe_writer.py`；
- 第一份 HUGSIM run report；
- 第一份 run report 的 Research Commander review；
- HUGSIM CUDA / pixi 环境问题定位与 runbook；
- HUGSIM 已 clone 到 `/home/yawei/HUGSIM`；
- Pixi 环境已使用 PyTorch 2.4.1+cu121 / CUDA 12.1 安装成功；
- 在 GPU 可见的非沙箱环境中验证了 CUDA tensor，以及 `gsplat`、`tinycudann`、`pytorch3d`、`hugsim_env` 导入；
- 已确认首选最小场景 `scene-0383.zip` 可单独下载，约 628 MB；
- 已确认 `scene-0383-easy-00.yaml` 的 `plan_list` 为空，第一轮无需下载完整 3DRealCar 车辆库；
- 已下载并校验 `scene-0383.zip`，SHA-256 为 `cbd99a927316f7f795904c59350b7fced4b8f32a14506891720962e3e30e7f15`；
- 已创建本地 smoke-test base config 与 bounded debug runner；
- 已跑通 3 个 deterministic closed-loop steps，覆盖 observation FIFO、plan FIFO、trajectory-to-control、ego update、连续渲染和评分；
- 已生成 `data.pkl`、`video.mp4`、`infos.pkl`、`eval.json`、`ground.ply`、`scene.ply`、完整 observation pickle 与 audit summary；
- 已生成第一条真实 audit record，判定为 `down-weighted`。
- 已发现 released `traj2control` 的坐标/航向不一致会把直行计划解释成约 90° 航向目标；
- 已实现不修改 HUGSIM 源码的 corrected control adapter，并增加 4 个回归测试；
- 已完成无车、横向0.0米静止车辆、横向3.5米静止车辆三组严格配对的5秒/20步实验；
- 三组 ego state 与 control action 最大差异均为 0；
- 无车和横向3.5米组 NC/TTC/PDMS 均为1.0；
- 已修复评分轨迹与评分帧前后时刻错位，并增加回归测试；
- 对齐重跑后，横向0.0米组 TTC 从2.75秒失败、NC 从3.75秒失败，PDMS 为0.557；
- 已完成 RGB / semantic / depth 像素级反事实比较和时序风险可视化；
- 横向0.0米车辆最终语义掩码有97.4%被 RGB 差异支持、100%被深度差异支持；
- 第三方复核后完整片段调整为 `down-weighted`，内部几何和严格配对子结论保留为 `accepted`；
- 已正式建立“日志复现、传感器一致性、任务级一致性、闭环结果可信性”四层可信证据链，并记录 HUGSIM 当前逐层状态。

第一份 run report 的结论是：

```text
not enough closed-loop evidence
```

原因是它只完成了环境层面的排障，没有生成 closed-loop segment。

第二份 run report 已完成：

```text
env.reset
→ obs_pipe
→ plan_pipe
→ env.step
→ output files
→ segment-level credibility judgment: down-weighted
```

第三份 counterfactual report 已完成：

```text
corrected no-actor baseline
→ lateral-0.0-m actor treatment
→ lateral-3.5-m position control
→ synchronized RGB / semantic / depth attribution
→ relation-level credibility judgment: down-weighted
```

其中 `accepted` 子结论只支持：

> 三组 ego state 和 action 严格一致，并且 HUGSIM 内部几何评分器对横向0.0米和3.5米两个精确位置产生不同响应。

完整片段因视觉域差异、缺少真实日志参考帧和真实 AD agent 而为 `down-weighted`。它不支持真实碰撞、AD agent 表现或 HUGSIM 全局可信结论。

---

## 7. 当前遗留问题

当前仍未完成：

- 在多个横向/纵向位置上验证 relation boundary 与指标单调性；
- 检查接近 TTC/NC 转换边界时，RGB / semantic / depth / geometry 是否仍一致；
- 验证移动 actor、遮挡变化和 risk-decreasing counterfactual；
- 接入真实 AD agent 后区分 agent response 与 simulator artifact；
- 跨场景验证当前 relation-level 结果；
- 在多场景、多关系证据成熟前，仍不定义最终 credibility metric。

---

## 8. 当前文件结构

核心文件：

- `README.md`
- `PROJECT_STATE.md`
- `SOURCE_AVAILABILITY_GATE.md`
- `docs/hugsim_audit.md`
- `docs/hugsim_smoke_test_plan.md`
- `docs/hugsim_credibility_decision_rules.md`
- `docs/log_driven_simulator_four_layer_evidence_chain.md`
- `docs/hugsim_four_layer_evidence_status.json`
- `docs/hugsim_cuda_pixi_runbook.md`
- `docs/runs/hugsim_smoke_test_001.md`
- `docs/runs/hugsim_smoke_test_001_review.md`
- `docs/runs/hugsim_smoke_test_002.md`
- `docs/runs/hugsim_smoke_test_002_audit.json`
- `docs/runs/hugsim_counterfactual_001.md`
- `docs/runs/hugsim_counterfactual_001_audit.json`
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
- `configs/hugsim/scenarios/scene-0383-adjacent-static-00.yaml`
- `configs/hugsim/nuscenes_smoke_base.yaml`

---

## 9. 需要重点审计的可信性缺口

重点不是 photorealism，而是 task-relevant relational consistency。

需要关注：

- front / rear / left / right 是否稳定；
- same-lane / adjacent-lane / off-road 是否正确；
- approaching / receding 是否可信；
- occluding / occluded-by 是否一致；
- actor scale / orientation 是否稳定；
- extrapolated views 是否出现 lane / drivable area artifact；
- risk-increasing / risk-decreasing 是否由传感器、几何、地图、时序证据支持；
- collision / near-miss 是模型真实失败，还是仿真 artifact；
- 高风险关系是否有足够证据支撑。

---

## 10. 长期工作流

不依赖单个超长聊天窗口。

推荐结构：

ChatGPT Project / Custom GPT  
+ `PROJECT_STATE.md`  
+ GitHub / Codex 仓库  
+ 文献矩阵  
+ 最小文档集合

聊天窗口负责研究判断，长期记忆落到项目文件中。

每轮讨论结束，应更新：

- 当前研究判断；
- 主线问题；
- 支线问题；
- 暂缓问题；
- 下一步最小行动。

---

## 11. 当前下一步最小行动

下一步只做：

> 为第一层日志复现建立真实日志锚点，据此加强第二层传感器一致性，并继续使用严格配对实验验证第三层任务级一致性。

当前关键不是增加无目的运行数量，而是回答：

1. 重建画面在原始采集位姿上与真实日志相差多少；
2. 偏离原始轨迹后，哪些区域仍有重建支持，哪些必须降权或拒绝；
3. 反事实 actor 修改是否保持几何、语义、遮挡和时序关系；
4. 闭环风险来自 agent、重建、场景编辑、控制接口还是评分实现；
5. 在前三层证据充分后，什么条件下才能把闭环结果用于自动驾驶系统评价。

不要同时展开 OmniDreams / Cosmos。
