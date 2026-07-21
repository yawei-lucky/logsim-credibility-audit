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

长期指导方针：

> HUGSIM 提供给智驾系统的任务相关信息，是否与现实一致到足以产生可信的感知、决策和闭环结果？

> 同一个智驾模型面对现实数据和对应的仿真数据，是否形成相近的感知、风险排序、规划和控制行为？

接收方可以是 AD 模型/系统，也可以是 human-in-the-loop 驾驶员。两类证据
互补，但不能无条件互相替代；验证应匹配仿真器预期服务的接收方和测试用途。

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

## 3. 当前工作流程

当前采用四步测试与证据处理路线：

### Step 1 — Source Availability Gate

先判断论文、代码、模型、数据、runtime、评估脚本是否公开可查。

### Step 2 — Closed-loop Evidence Completeness

判断一次闭环仿真是否产生了完整证据链，包括 observation、planner output、action、ego / actor state update、metrics 和输出文件。

### Step 3 — Segment-level Evidence Judgment

对单个 closed-loop segment 做 evidence qualification：

- accepted；
- down-weighted；
- rejected。

这里的 accepted / down-weighted / rejected 是当前阶段的证据处理方式，可用于场景筛选和证据质量管理；它不是项目总目标，也不是最终数值指标。

判定以具体主张为单位。`rejected` 不等于实验无效：原行为主张可以被拒绝，
同时由同一实验支持一个 `accepted` 的仿真器或指标诊断发现。每条拒绝主张
必须记录是否实际测试、拒绝依据和证据引用；未测试与超范围不构成能力失败。

### Step 4 — Future Credibility Metric

在积累多个 run 和多个 segment 后，再定义量化的 simulator credibility metric。

当前不急于提出最终数值指标。先保证证据链和判定规则成立。

长期的可信评价指标计划沿四层证据链研究：

```text
日志复现
→ 传感器一致性
→ 任务级一致性
→ 闭环结果可信性
```

这四层是未来指标的证据组织思路，不是当前项目阶段，也不用于现在给 HUGSIM 逐层打分。当前工作仍是测试、对照、证据积累和因果归因，尚未进入指标设计。

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
- 已明确未来可信评价指标计划采用四层证据链，但当前尚未进入指标设计或逐层评分阶段。
- 已按用户明确调整完成 6 秒/24 步多车强干预实验：一辆前方慢车和一辆右侧斜向切入车；
- 多车组与无车组 ego state、action 最大差异均为 0；
- 该 6 秒 run 的 raw 输出显示 TTC 从 4.75 秒、NC 从 5.75 秒失败；
- 多车组 PDMS 为 0.798、HDScore 为 0.148，无车组分别为 1.0 和 0.185；
- 已生成多车前视三联视频、五时刻跨模态图、俯视轨迹和风险时间线；
- 独立证据审查发现 6 秒多车 run 的 TTC/NC 失败全部位于缺少 2.5 秒
  未来 actor 历史的尾窗，评分器用末帧 actor box 填充未来；
- 将完全相同的 state/action/plan 前缀延长到 9 秒后，旧 TTC/NC 失败全部
  消失，旧内部风险时序结论已改为 `rejected`；
- 已完成无车、仅前车、仅远距切入、前车+远距切入四组 9 秒
  actor-removal 实验，完整时域窗口内四组 NC/TTC/PDMS 均为 1；
- 已完成一次执行前固定参数、无事后调参的近距汇入：3.917 秒过中心线，
  5.5 秒二维有向 footprint 净距 0.730 米，无实际碰撞；
- 近距组在完整未来窗口内 NC=1、TTC=0.115、PDMS=0.368，23 个 TTC
  失败全部命中 actor0 且无尾部填充；
- 已增加 fail-closed 配对/时域分析、writer 同值 `Done` 握手、严格
  runner 成功状态、claim/diagnostic 双层语义校验与 28 个回归测试；
- 已由实验设计、证据和可复现性三个 task-local 独立 Codex reviewer
  角色复核 rejected 语义，明确区分被拒绝的主张与被接受的系统/指标
  诊断发现；这不是外部人类第三方评审记录；
- 运行级技术问题继续保留用于复现和结果有效性检查，但不作为理论框架的
  核心研究发现；HUGSIM TTC 的构念边界仍需在后续指标解释中明确。
- 已建立真实日志 Source Anchor Gate：`scene-0383` 的发布元数据包含180个
  时刻、六相机1080条标定/位姿记录和36个按当前 reader 规则推导的
  测试候选，但本地缺少全部真实 RGB、原始 nuScenes token 与 ASAP
  `interp_12Hz_trainval` 映射；
- 已确认现有闭环相机模板与重建源相机并非严格匹配，不能将当前 rollout
  当作 matched-pose real-sim 对照；
- 已形成 matched receiver 计划，分别进行 AD 内和 human-in-the-loop 内的
  real-vs-sim 配对，再比较共同任务变量和干预效应方向。

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

第四份 multi-actor report 已完成：

```text
6-second no-actor baseline
→ lead vehicle + scripted right-side cut-in
→ synchronized RGB / semantic / depth and actor-state evidence
→ TTC failure at 4.75 s and NC failure at 5.75 s
→ actual runtime collision: false
→ multi-actor credibility judgment: down-weighted
```

第四份报告的 raw 输出保留，但动态风险解释已纠正。旧失败全部发生在
3.5 秒后的 horizon-invalid 尾窗；相同前缀延长后均不失败。因此只保留
严格配对、多实例渲染和状态连续性，旧 NC/TTC 风险主张为 `rejected`。

第五份 rollout-horizon / factorial report 已完成：

```text
6-second run with incomplete future actor history
→ exact-prefix 9-second extension
→ 2×2 actor-removal controls
→ all valid-window metrics equal 1
→ finite-rollout tail artifact: accepted
```

第六份 near-distance cut-in report 已完成：

```text
pre-specified single-shot treatment
→ centerline crossing at 3.917 s
→ 0.730 m positive 2D footprint clearance
→ horizon-valid TTC=0.115, NC=1
→ 23 actor0-specific failures, no padding
→ overall down-weighted; narrow internal TTC response accepted
```

两辆 actor 仍复用同一个本地 3DRealCar 资产；切入仍是无地图约束的
`ConstantPlanner` 直线轨迹；deterministic writer 不响应车辆。因此新结果
证明的是内部渲染/几何/评分响应，不是交通行为真实性或 AD agent 能力。

---

## 7. 当前遗留问题

当前仍未完成：

- 获取 `scene-0383` 对应的授权 nuScenes 原始相机数据和 ASAP 12Hz映射，
  建立第一组严格 matched-pose factual anchor；
- 使用不同车辆身份和地图约束控制器验证更可信的汇入、遮挡与 risk-decreasing counterfactual；
- 接入真实 AD agent 后区分 agent response 与 simulator artifact；
- 跨场景验证当前 relation-level 结果；
- 把 horizon-valid gate 推广到其它 HUGSIM 运行和评分事件；
- 发布可从 fresh clone 下载的紧凑证据包；
- 在多场景、多关系证据成熟前，仍不定义最终 credibility metric。

---

## 8. 当前文件结构

核心文件：

- `README.md`
- `PROJECT_STATE.md`
- `SOURCE_AVAILABILITY_GATE.md`
- `docs/hugsim_audit.md`
- `docs/research_guiding_principles.md`
- `docs/hugsim_matched_receiver_validation_plan.md`
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
- `docs/runs/hugsim_horizon_factorial_001.md`
- `docs/runs/hugsim_horizon_factorial_001_audit.json`
- `docs/runs/hugsim_near_cut_in_001.md`
- `docs/runs/hugsim_near_cut_in_001_audit.json`
- `docs/runs/hugsim_source_anchor_gate_001.md`
- `docs/runs/hugsim_source_anchor_gate_001.json`
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
- `scripts/validate_hugsim_audit_semantics.py`
- `scripts/audit_hugsim_source_anchor.py`
- `scripts/analyze_hugsim_counterfactual.py`
- `scripts/analyze_hugsim_multicar.py`
- `scripts/analyze_hugsim_horizon_factorial.py`
- `scripts/analyze_hugsim_near_cutin.py`
- `configs/hugsim/scenarios/scene-0383-adjacent-static-00.yaml`
- `configs/hugsim/scenarios/scene-0383-multicar-cut-in-00.yaml`
- `configs/hugsim/scenarios/scene-0383-lead-only-00.yaml`
- `configs/hugsim/scenarios/scene-0383-cut-in-only-00.yaml`
- `configs/hugsim/scenarios/scene-0383-near-cut-in-00.yaml`
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

本轮切入参数实验已经满足执行前停止标准，下一步不再调整同一场景参数。

下一步只在以下方向中选择一个有材料提升的动作：

1. 下载不同 3DRealCar 身份并使用更可信的地图约束/分阶段行为；
2. 跨场景复核 horizon-valid metric gate；
3. 转向真实源日志锚点，开始验证 matched-pose 重建与真实观测的一致性。

在用户选择前，优先维护当前证据、工具和判定规则，不自行扩展到完整 benchmark、
真实 AD agent 或最终可信指标。

不要同时展开 OmniDreams / Cosmos。
