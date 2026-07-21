# Log-Driven Counterfactual Closed-Loop Simulation Credibility Audit

本项目研究 **日志驱动、可反事实修改、传感器级输入、闭环交互** 的自动驾驶仿真器可信性问题。

总目标不是复现某篇论文的分数，也不是判断生成画面是否足够逼真，而是建立一套用于审计闭环仿真证据的研究方法：

> 仿真器生成的闭环测试结果，是否足以作为评估端到端自动驾驶模型的可信证据？

项目的两条长期指导方针是：

> HUGSIM 提供给智驾系统的任务相关信息，是否与现实一致到足以产生可信的感知、决策和闭环结果？

> 同一个智驾模型面对现实数据和对应的仿真数据，是否形成相近的感知、风险排序、规划和控制行为？

接收方既可以是自动驾驶模型/系统，也可以是 human-in-the-loop 驾驶员。
人类行为证据与机器接收方证据互为补充；面向哪类接收方建立测试域，就应当
用对应接收方验证。详见 `docs/research_guiding_principles.md`。

## 日志驱动定义

本项目采用广义定义：

> 日志驱动仿真器以真实道路采集序列为基础，重建或构造可交互环境，并在其上生成反事实闭环过程；不要求简单回放原始日志。

因此 HUGSIM 属于研究范围，更准确地说是**基于真实驾驶数据序列重建、支持反事实编辑的闭环神经仿真器**。真实数据来源不意味着新视角、插入车辆和未来交互天然可信，这正是本项目要验证的问题。

## 当前阶段目的

当前阶段使用 **HUGSIM** 作为实验载体。最小闭环证据链已经跑通，当前工作已进入严格配对的 relation-level counterfactual audit。

在继续增加场景或接收方之前，当前优先采用“路线 B：先审计指标”。
`docs/hugsim_metric_evidence_map.md` 记录已有量到底测量什么、来源是否独立、
能够支持和不能支持哪些主张，以及升级为真实—仿真证据所需的参考。
HUGSIM 输出的 RGB、semantic 和 depth 都是待验证的仿真输出；semantic/depth
可用于内部诊断，但不默认作为可信 ground truth。

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

判定对象是具体主张，不是给整次实验贴“成功/失败”标签。若设定预期与
仿真结果不一致，可以同时得到：

- 原主张 `rejected`；
- 关于仿真器、指标或实验构造缺陷的诊断结论 `accepted`。

每条 rejected 主张都必须注明是否实际测试、拒绝依据和证据引用；
`not_tested` 与 `scope_exceeds_evidence` 不允许被解释为 HUGSIM 能力失败。

长期的可信评价指标计划沿四层证据链研究：**日志复现、传感器一致性、任务级一致性、闭环结果可信性**。这四层是未来指标的证据组织思路，不是当前实验阶段，也不用于现在给 HUGSIM 逐层打分。当前仍先完成测试、对照、证据积累和因果归因。

## 当前状态

当前直接路线是 **Route B：指标审计与证据地图**。此前的配对反事实实验、
proxy 曲线和接收方一致性结果都保留为审计材料，但不再自动推动新增 proxy，
也不替代真实—仿真一致性证据。执行依据以
`docs/hugsim_metric_evidence_map.md`、`CODEX_NEXT_TASK.md` 和
`PROJECT_STATE.md` 的最新表述为准。

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
- 通过独立复核发现并复现 HUGSIM 末帧 actor 状态填充造成的
  NC/TTC 尾窗伪影，撤回旧的内部风险时序结论；
- 无车、仅前车、仅远距切入、前车+远距切入四组严格配对的 9 秒
  actor-removal 实验；
- 一次执行前固定参数的近距汇入强干预：0.730 米二维 footprint 正净距、
  无碰撞、完整未来时域内 TTC 明显响应；
- fail-closed 配对/时域检查、同值 FIFO 结束握手、claim/diagnostic
  语义校验、AD readiness 与 matched-pose manifest，以及 36 个回归测试。
- scene-0383 真实日志 Source Anchor Gate 与 matched receiver 对照计划；
- 已确认发布场景只有1080条六相机标定/位姿索引，没有对应真实RGB和源
  token，因此当前还没有严格 real-sim pair。
- AD receiver readiness inventory；该次清点时本机只有 `scene-0383` 一个
  HUGSIM scene，真实 RGB 为 0/1080，source identity 不完整，因此尚不能做
  同一 AD receiver 的 real-vs-sim 输入对比；后续新增重建包没有改变真实
  source 缺失的判断。
- `scene-0383` frame00004 matched-pose manifest；已固定第一候选帧的六相机
  exact metadata K / camtoworld、native dynamic policy 和 camera-only
  receiver contract，但 source anchor 仍 blocked。
- AD receiver proxy stress test；已生成远距同车道、近距同车道、相邻车道和
  多车合流四组新的 HUGSIM rollout，并用固定 CAM_FRONT 语义/深度接收方代理
  验证距离、车道关系和多车合流的任务信号方向。三个方向检查为 accepted，
  但整体仍为 down-weighted，因为这不是实际 AD agent response，也不是
  matched real-sim comparison。
- Frozen camera detector stress test；已用 torchvision Faster R-CNN
  MobileNetV3 COCO 权重，只输入 CAM_FRONT RGB，对同五组 rollout 输出
  boxes、confidence、简单跟踪连续性和 image-plane risk ranking。三个方向
  检查同样 accepted，同时保留 no-actor 中 4/37 帧背景/边缘道路对象检测的
  边界发现；整体仍为 down-weighted，因为这不是完整 AD stack 或 real-sim
  matched comparison。
- Cross-receiver task-response agreement；已对齐 semantic/depth proxy 和
  RGB detector 的中心路径任务信号。两个接收方在近距/远距、同车道/相邻车道、
  多车合流三个方向上全部一致，run-level Spearman=1.0；整体仍为
  down-weighted，因为这是 HUGSIM 内部接收方一致性，不是 real-sim 证据。
- 两个补充正常场景已完成官方资产校验和 36 步六相机 RGB/semantic/depth
  bounded run：`scene-0041` 覆盖信号十字路口，`scene-0138` 覆盖弯道、
  学校区域、路侧目标和遮挡。它们用于扩展指标审计条件，不代表可信性结论。
- 正常场景 sensor/receiver 指标审计；六相机数组/标定基本契约和深度数值
  有效性 accepted，跨模态边界共变 down-weighted；同时发现当前 center-path
  risk proxy 会被自车车头及路侧假汽车检测主导，其跨场景稳健性主张 rejected。

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

旧 6 秒多车结果因评分时域不完整而不再用于风险结论。具体原因保留在运行
报告中，作为复现和结果有效性检查，不作为当前理论研究的核心发现。

修正后的 9 秒四条件实验在完整未来窗口 0.25–6.5 秒内 NC/TTC/PDMS
全部为 1.0，证明原远距切入只是穿越中心线，并未形成有效近距事件。

随后只运行了一次执行前固定参数的近距汇入。它在 3.917 秒穿越中心线，
5.5 秒达到 0.730 米二维有向 footprint 正净距；runtime collision 和 NC
均不失败，但完整未来窗口内 TTC 为 0.115、PDMS 为 0.368，23 个 TTC
失败全部命中切入 actor0 且未使用尾部填充。这个内部 TTC surrogate
响应子结论为 `accepted`，完整片段仍为 `down-weighted`。

最新的 AD receiver readiness 清点没有生成新场景或新 rollout。它验证的是
当前本机资产是否能进入“同一个 AD 模型面对真实数据和对应仿真数据”的核心
对比试验。结果为 blocked：本地仅有 `scene-0383`，真实 RGB 为 0/1080，
source identity 不完整，现有闭环相机也不是 exact matched-pose render。

最新的 matched-pose manifest 也没有生成新场景、新 rollout 或新渲染图。它把
后续 exact-pose render 的第一候选固定到 `scene-0383` 的 `frame00004`
（t=0.333595s），记录六相机 K / camtoworld / resolution / native dynamic
ID，并附带 `camera_only_rgb_single_frame_v0` receiver contract。由于真实 RGB
和 source identity 仍缺失，pairing gate 仍为 `blocked_source_anchor`。

最新的 AD receiver proxy stress test 已经生成新场景、新 rollout 和可视化。
它不是为了证明 HUGSIM 可信，而是把当前工作推进到“同一冻结接收方面对不同
仿真反事实输入时，任务相关输出是否沿正确方向变化”的结构。结果和路径见：

```text
docs/runs/hugsim_ad_receiver_proxy_001.md
artifacts/hugsim_ad_receiver_proxy/scene-0383-ad-receiver-proxy-run001
```

最新的 frozen camera detector stress test 进一步只用 RGB 接收方进行验证，
路径为：

```text
docs/runs/hugsim_camera_detector_001.md
artifacts/hugsim_camera_detector/scene-0383-camera-detector-run001
```

最新的 cross-receiver agreement 结果把两个接收方放在同一任务变量上对齐：

```text
docs/runs/hugsim_receiver_agreement_001.md
artifacts/hugsim_receiver_agreement/scene-0383-receiver-agreement-run002
```

## 当前重点

当前这轮多车参数实验已按事前停止标准结束，不再继续调位置追结果。随后新增
的 AD receiver proxy stress test 已建立了一个新的推进链路：

```text
exact pairing
→ complete future actor history gate
→ far cut-in negative control
→ positive-clearance near cut-in
→ actor-specific TTC attribution
→ claim-specific accepted / down-weighted / rejected judgment
→ frozen task receiver proxy
→ distance / lane / multicar causal direction checks
→ frozen RGB camera detector
→ boxes / confidence / tracking / risk-ranking checks
→ cross-receiver task-response agreement
```

下一次如继续 HUGSIM，优先接入一个驾驶域冻结 camera-only AD 感知模型，复用
当前五组输入和输出 schema，与语义/深度代理和 COCO 检测器做对照；真实源
日志锚点仍是后续 matched real-sim 对比的关键 gate。不要继续修改同一切入
参数追结果。

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
- `docs/runs/hugsim_ad_receiver_readiness_001.md`
- `docs/runs/hugsim_ad_receiver_readiness_001.json`
- `docs/runs/hugsim_matched_pose_manifest_001.md`
- `docs/runs/hugsim_matched_pose_manifest_001.json`
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
- `scripts/analyze_hugsim_horizon_factorial.py`
- `scripts/analyze_hugsim_near_cutin.py`
- `scripts/validate_hugsim_audit_semantics.py`
- `scripts/audit_hugsim_source_anchor.py`
- `configs/hugsim/nuscenes_smoke_base.yaml`
- `configs/hugsim/scenarios/scene-0383-adjacent-static-00.yaml`
- `configs/hugsim/scenarios/scene-0383-multicar-cut-in-00.yaml`
- `configs/hugsim/scenarios/scene-0383-lead-only-00.yaml`
- `configs/hugsim/scenarios/scene-0383-cut-in-only-00.yaml`
- `configs/hugsim/scenarios/scene-0383-near-cut-in-00.yaml`

## 项目判断

HUGSIM 是当前实验载体；真正目标是形成 **closed-loop simulation credibility audit methodology**。

当前阶段的关键问题是：

> 一次闭环仿真结果在什么证据条件下可以被 accepted，什么时候应该 down-weighted，什么时候必须 rejected？
