# HUGSIM 指标审计与证据地图

> 状态：当前研究路线。先审计已有指标测量的对象和证据边界，再增加接收方、场景或曲线。
>
> 本文不是最终可信性指标，也不对 HUGSIM 进行逐层打分。长期四层证据链仍是日志复现、传感器一致性、任务级一致性和闭环结果可信性。

## 1. 为什么先审计指标

当前实验已经证明若干受控干预能够让 HUGSIM 内部状态、渲染输出和接收方输出产生可重复变化。但“指标随干预变化”不等于“指标测到了风险”，更不等于“仿真器可信”。

指标审计首先回答：

1. 指标直接测量的构念是什么；
2. 输入来自现实观测、仿真器内部状态、渲染输出、第三方模型还是自定义映射；
3. 参考依据是否独立于被验证的仿真器；
4. 指标能够支持和不能支持哪些主张；
5. 需要什么对照，才能把内部一致性升级为真实—仿真可信性证据。

## 2. 证据层级

```text
World / independent reference
→ Geometry and dynamics
→ Rendering / sensor outputs
→ Perception
→ Scene and task understanding
→ Planning
→ Control and closed-loop outcome
```

层级越靠后，越接近“能否作为智驾测试域”的最终问题，但后层不能自动修复前层错误。规划结果看似合理，也不能反向证明深度、语义或遮挡关系正确。

## 3. 当前指标证据地图

| 层级 | 指标或输出 | 来源 | 直接测量什么 | 当前能支持什么 | 当前不能支持什么 | 升级证据所需参考 |
|---|---|---|---|---|---|---|
| Geometry | Actor 3D box、ego/actor pose | HUGSIM 内部状态 | 仿真器声明的几何状态 | 运行配对、轨迹连续性、内部间距计算 | 几何状态符合现实；渲染位置正确 | 独立日志标注、测量或受控场地真值 |
| Geometry / outcome | NC、DAC、TTC surrogate、PDMS、HDScore | HUGSIM 评分器 | 内部几何、地图、计划轨迹和车辆状态下的 AD 表现 | 在完整未来时域内描述 HUGSIM 内部评分结果 | 物理 TTC；传感器正确；仿真器整体可信 | 独立重算、现实或受控场地结果、有效时域检查 |
| Rendering | RGB | HUGSIM 渲染器 | 虚拟相机像素输出 | AD 实际可接收的视觉输入；可检查可见性和外观变化 | RGB 与真实相机一致；任务信息充分 | 同位姿、同标定、同时刻真实 RGB 和相同接收方 |
| Rendering | Semantic mask | HUGSIM 渲染器 | 渲染器声明的像素类别 | 内部对象可见区域、跨模态诊断 | 语义标签真实正确；可作为独立真值 | 独立真实标注或独立标注流程；跨视角与时序检查 |
| Rendering | Depth map | HUGSIM 渲染器 | 渲染器声明的像素深度 | 内部深度排序、遮挡和几何诊断 | 真实尺度深度正确；可作为独立真值 | 匹配 lidar/stereo/测量参考及误差区间 |
| Rendering | Array / calibration contract | HUGSIM observation + `cam_params` | 六相机数组形状、数据类型、内外参格式与时间内稳定性 | 接收方接口完整；标定数值在内部满足基本代数约束 | 跨相机看到同一世界点；标定符合真实传感器 | 独立标定、公共三维对应点和重投影误差 |
| Rendering | RGB—semantic—depth boundary co-variation | 自定义边界诊断，三种输入均来自 HUGSIM | 语义边界附近是否有 RGB 梯度或深度断层 | 定位跨模态内部错位疑点和困难相机 | 任一模态真实正确；真实传感器一致性 | 独立 RGB/标签/depth、固定容差和任务影响对照 |
| Perception | Vehicle area / center-path occupancy | 自定义 semantic proxy | 投影占用和中心区域重叠 | 目标变大、进入或离开选定图像区域 | 危险程度、交通复杂度、规划必要性 | 独立几何投影；真实—仿真同接收方响应 |
| Perception | Median depth of top component | 自定义 semantic/depth proxy | 当前最显著组件的典型深度 | 单个显著目标的远近变化 | 多车数量或交通复杂度；物理碰撞风险 | actor 对应关系、top-k 深度、独立深度参考 |
| Perception | Detector confidence | 冻结 COCO detector | 模型对类别判断的确信程度 | 目标是否被通用检测器稳定识别；检查背景/渲染 artifact 是否诱发响应 | 危险程度、车道关系、规划动作 | 驾驶域接收方、真实—仿真成对误差和误检基线 |
| Perception | Bbox scale、count、temporal IoU | 冻结 detector + 自定义统计 | 图像投影大小、检测数量和框连续性 | 感知响应随距离、多车和时间的变化 | 真实距离、完整跟踪、风险或控制正确 | 3D/2D 独立参考、身份跟踪、真实匹配片段 |
| Perception / relation | Sparse4Dv3 车辆 3D box、score 和时序 instance | 冻结 nuScenes camera-only 3D receiver；输入为 HUGSIM 六相机 RGB 与标定 | 驾驶域模型从仿真 RGB 恢复的车辆类别、位置和时序响应 | 受控车辆是否引发响应；near/far、same/adjacent 关系方向；接收方 nuisance baseline | HUGSIM 内部 box 是现实真值；单接收方误差可归因于渲染器；规划或安全结果可信 | 匹配真实日志上的同一接收方输出、独立 3D 标注、标定/坐标审计及第二接收方复核 |
| Task | Center-path risk proxy | 自定义加权函数 | confidence、中心重叠、图像底部位置和框大小的组合 | 当前受控场景的排序诊断 | 校准风险概率、物理 TTC、制动必要性 | 冻结构念与权重；独立任务标签；真实—仿真等效性界限 |
| Task | Cross-receiver rank agreement / Spearman | 自定义跨接收方统计 | 两个接收方对少量场景的排序一致性 | 不同输入通道是否给出相同干预方向 | 两者都正确；真实—仿真一致；规划一致 | 独立真实参考、更多预先规定条件、置信区间 |
| Task / robustness | Designed-counterfactual conclusion stability | 已获资格的物理/因果约束、不同失败模式接收方与参数敏感性分析 | 任务关系、关键目标排序或动作结论是否在声明的不确定性范围内保持稳定 | 无精确现实对应物场景的有边界因果一致性、压力测试适用性和模型稳健性 | 该未来是唯一现实结果；直接 real-sim 等效；未覆盖范围内的安全性 | 指标/接收方外部资格证据、合理不确定性范围、依赖性审计和下游任务边界 |
| Planning | 候选轨迹分数与最终 ego 轨迹 | SparseDrive-S Stage2 已选定、尚未接入；VAD-Tiny 仅作后续架构复核 | 冻结 AD 的原生开环规划输出 | 已完成模型与输出构念的接入前资格审计；尚无 HUGSIM 规划结果 | 显式关键目标身份、校准风险概率、制动/转向控制或规划一致性结论 | 先通过六相机、虚拟 LiDAR/ego 参考帧、时序、10-D ego status、未来轨迹条件标签与状态重置合同；再做预注册反事实方向实验，之后补真实数据或第二架构证据 |
| Control / outcome | brake、steer、干预时间、碰撞和任务结果 | 目标 AD/controller，尚未接入 | 控制行为和闭环结果 | 尚未形成当前证据 | 真实车辆闭环可信性 | 匹配闭环参照或受控场地、车辆动力学、已获资格的任务边界和不确定性范围 |

## 4. 指标自身的审计门槛

每个准备进入正式对照实验的指标至少记录以下内容：

| 审计项 | 要回答的问题 |
|---|---|
| Construct | 它实际测量的是占用、距离、识别确信、任务关系、决策还是结果？ |
| Provenance | 输入来自 HUGSIM 内部状态、渲染输出、第三方接收方还是人工定义？ |
| Independence | 参考是否独立于 HUGSIM？是否用 HUGSIM 的输出验证同一输出？ |
| Receiver contract | 真实和仿真是否送入同一个冻结接收方，模态、标定、时序和接口是否相同？ |
| Causal sensitivity | 距离、车道、遮挡或运动变化时，指标方向是否符合预先规定的关系？ |
| Nuisance robustness | 光照、纹理、重建 artifact 和背景是否会改变结论？ |
| Temporal validity | 是否有完整历史和未来窗口，是否存在末帧填充或身份跳变？ |
| Claim boundary | 该指标能支持的最强主张是什么，哪些更强主张必须拒绝？ |

对语义和深度尤其执行以下原则：

> HUGSIM semantic/depth 是待验证的仿真输出，不是默认可信的 ground truth。

它们可以用于内部一致性诊断，但只有经过独立现实参考、几何尺度、遮挡、跨视角和时间一致性验证后，才可以在相应范围内支持传感器可信性主张。

## 5. 接收方实际输入的展示规则

对于 camera-only AD 接收方，报告至少一次展示其实际收到的原始相机数组，并记录相机名、帧号、时间戳、分辨率和文件哈希。人看到的图和交给 AD 的数组必须来自同一数据对象或可验证的同一字节内容。

常规报告无需展示模型内部 resize、normalization 或 feature tensor；这些处理记录在 receiver contract 中即可。若接收方使用六相机，则展示六相机原始输入，而不能用单前视图代表完整接收方输入。

HUGSIM 的 semantic/depth proxy 与 RGB AD 接收方保持分开：前者是仿真器内部输出审计工具，后者是目标接收方输入。二者一致只能形成跨通道诊断证据，不能替代各自的现实参考验证。

当前一次性输入核验见 `docs/runs/hugsim_receiver_input_inspection_001.md`：保存图与冻结 RGB detector 实际读取的是同一个 `CAM_FRONT` 原始数组，展示图未叠加检测框。

## 6. 当前路线 B 的执行顺序

1. 冻结本证据地图，逐项纠正已有图表和报告的过强解释；
2. 对 RGB、semantic、depth、内部 3D geometry 和 HUGSIM 评分器建立来源及依赖关系；
3. 选择少量能够回答大方向问题的指标，明确其资格依据、独立性、误差范围和允许主张；
4. 场景级真实锚点可用时，使用同一冻结 AD 接收方做匹配真实—仿真比较，形成直接等效性证据；
5. 没有精确现实对应物的人工反事实也可推进，但必须使用已获资格的指标/约束，报告模型不确定性敏感性，并把主张限制为因果一致性和有边界的任务稳健性；
6. 将 matched factual 和 designed counterfactual 作为两条互补证据路径，而不是要求所有反事实按单一串行顺序等待；
7. 最后进入 planning、control 和闭环结果，不用 perception proxy 提前替代它们。

当前已有 proxy、detector 和 cross-receiver 曲线保留为指标审计材料，不作为 HUGSIM 可信性的最终结果。

现实锚定由此分为两级：单个场景的匹配事实起点是强证据但非普遍前提；指标和
验证工具的框架级外部效度不可取消。若一项指标只由 HUGSIM 输出定义并只在
HUGSIM 输出上证明自己，它最多支持内部一致性诊断，不能支持现实等效。

## 7. 两个补充正常场景的最新审计

`scene-0041` 与 `scene-0138` 的 37 帧六相机正常运行已经进入本地图，详见
`docs/runs/hugsim_normal_scene_sensor_audit_001.md`。

| 审计对象 | `scene-0041` | `scene-0138` | 当前解释 |
|---|---:|---:|---|
| 六相机数组/标定基本契约 | accepted | accepted | 只证明接口和内部代数约束 |
| 深度非有限或非正像素 | 0 | 0 | 数值有效，不证明尺度真实 |
| 语义边界靠近深度断层，六相机均值 | 0.756 | 0.461 | 后者内部共变明显较弱，作为定位疑点，不作真实性阈值 |
| RGB 语义边界/内部梯度比，六相机均值 | 4.19 | 1.79 | 后者边界外观区分度较弱，需检查是否影响接收方 |
| 冻结 detector 有输出的前视帧 | 16/37 | 2/37 | 两者均包含背景或渲染内容响应，不能按 actor 注入数量解释 |

最关键的新审计发现是：`scene-0041` 的现有 center-path risk proxy 峰值由
“自车车头/底部模糊区域被识别为近处汽车”产生，而不是前方真实可见卡车；
`scene-0138` 的两次低置信汽车检测落在路侧植被/标牌附近。因此 detector
response 可以作为 nuisance sensitivity 诊断，但当前 risk proxy 不具备跨场景
稳健性，不能进入正式安全或可信性结论。

## 8. 首个驾驶域 3D 接收方基线

`docs/runs/hugsim_sparse4d_receiver_baseline_001.md` 已将冻结的官方
Sparse4Dv3 R50 接到六相机 HUGSIM RGB。该接收方不读取 HUGSIM semantic 或
depth，也没有在 HUGSIM 上微调。

| 审计量 | no actor | front far | front near | adjacent near | 当前判断 |
|---|---:|---:|---:|---:|---|
| qualified vehicle 阳性帧率 | 5.3% | 100% | 100% | 94.7% | 注入敏感性 accepted |
| receiver median x (m) | n/a | 19.41 | 9.46 | 1.55 | near/far 方向 accepted |
| receiver median y (m) | n/a | 0.34 | 0.15 | -6.59 | same/adjacent 方向 accepted |
| receiver—HUGSIM actor median XY error (m) | n/a | 2.56 | 4.24 | 3.80 | 绝对位置一致性 down-weighted |

这组结果说明当前指标审计路线能够同时保留正面与负面证据：HUGSIM 图像足以
让真实数据训练的 3D 接收方产生正确的因果方向和关系排序，但绝对 3D 位置偏差
仍然显著。偏差目前不能唯一归因于渲染、标定/坐标适配或接收方 domain shift。

因此当前最强主张仅限于 bounded task-response / relation-direction evidence；
real—sim equivalence、规划控制和仿真器整体有效性仍未测试。

## 9. 跨场景汇总后的指标收敛

完整定义见 `docs/simulator_credibility_indicator_convergence.md`，实验见
`docs/runs/hugsim_sparse4d_cross_scene_001.md`。

当前 Sparse4Dv3 结果定位为 **task-level receiver-consistency candidate**，
不是 sensor consistency。六相机数组和标定检查当前只形成 receiver input
contract；没有匹配真实 RGB 或独立传感器参考，不能升级为传感器一致性。

当前保留的最小指标族为：

| 指标族 | 当前端点 | 当前用途 |
|---|---|---|
| Evidence validity gate | 输入身份、冻结接收方、相机/时间/预处理、完整历史未来窗口 | 先判断证据是否有效，不计质量分 |
| Observability / sensitivity | 目标阳性帧率、漏检时长、paired intervention effect | 判断任务信息是否到达接收方 |
| Relation / ordering | same/adjacent、near/far、top-risk identity | 判断任务关系和排序是否保持 |
| Metric / temporal | XY/速度误差、track dominant fraction、identity switch | 判断量值和时序是否足以支持下游任务 |
| Nuisance robustness | 跨场景、阈值稳定性、标注干扰区域假响应 | 判断结果是否被背景或重建 artifact 主导 |
| Matched real-sim equivalence | 同一冻结接收方的 paired differences 和 action invariance | 未来可信性升级 |

当前受控端点为 near/far 6/6、车道关系 43/44，dominant track fraction 为
100%/83%/100%；这些支持粗粒度 presence/relation/ordering/short tracking。
近车纵向偏差约为其设定中位距离的 81%，邻车横向偏差约为 4 米设定偏移的
65%，所以不能据此接受面向规划的米制 3D 定位。

框偏差诊断进一步发现：Sparse4Dv3 3D 框回投到注入车辆区域的中位 2D IoU
仍为 0.69/0.74/0.82，而接收方估计的车体尺寸明显更大。这支持内部的
scale-depth/domain-shift 诊断，说明 gross image-plane projection failure 不太可能
是唯一原因；但 HUGSIM semantic 和标定并非独立真值，因此该机制解释仍为
down-weighted。

## 10. 正常场景可见性标注审计

`docs/runs/hugsim_sparse4d_normal_scene_annotation_001.md` 已把正常场景的无标注
response count 推进为固定小样本的人眼可见性审计。事先冻结 `scene-0041`、
`scene-0138` 首/中/末帧和 score >= 0.2 的全部 Sparse4Dv3 输出，共 14 个：
7 个有渲染 RGB 中可见目标支撑，7 个落在路缘、植被、相机边界或重建拖影上。

该结果接受样本身份、输入哈希和“固定样本中 7/14 有可见支撑”这一可复查事实，
拒绝“固定样本中所有输出均对应可见目标”的具体主张；作为仿真器有效性证据仍
down-weighted。标注只查看 HUGSIM RGB，虽然独立于 HUGSIM semantic/depth 和
内部 actor state，却不是独立现实参考。样本又是 detection-conditioned，不能
测量漏检或 recall，也不能把 50% 写成 ODD precision。

因此 nuisance robustness 作为任务级指标族被保留，但接受阈值不能来自本次小
样本比例；下一步需先声明一个 critical-object / lane-relation / risk-order 下游
决策边界，再判断哪些误响应会改变 AD 决策。

## 11. 验证工具资格审计 001

本节完成下一阶段的第一轮“先验证尺子”审计。表中的“下一实验用途”是工具
使用范围，不是新的 segment-level evidence label；具体实验仍只使用
`accepted`、`down-weighted`、`rejected` 裁决具体主张。

| 工具或参考 | 直接测量的构念 | 外部效度与 HUGSIM 依赖 | 下一实验用途 | 当前最强允许主张 | 最小资格缺口 |
|---|---|---|---|---|---|
| Source / exact-pairing gate | 源数据可用性、身份、位姿、时间和输入一一配对 | 依赖不可变 source identity、哈希和独立真实观测，不依赖 HUGSIM 质量结果 | 直接 real-sim 分支的强制 gate；当前 blocked | 当前只有 metadata 候选，尚无 real-sim pair | 原始六相机 RGB、nuScenes token、ASAP 映射和 checkpoint split provenance |
| Run identity / complete-future horizon gate | 运行同一性、计划/状态前缀和评分未来时域是否完整 | 使用直接日志、哈希、时间索引和独立重算；读取 HUGSIM 记录但不以其评分结论自证 | 所有后续实验的强制有效性 gate | 某段证据可复现、严格配对且未被尾窗填充污染 | 无法单独提供现实性或任务正确性 |
| 独立重算的二维 footprint、净距和相对关系 | 给定 box 下的碰撞/正净距、中心线穿越、near/far 和 lateral ordering | 算法基于欧氏/刚体几何，独立于 HUGSIM scorer；输入 box 仍来自 HUGSIM | 可作为 designed counterfactual 的干预有效性约束 | 在仿真器声明状态成立的前提下，干预具有指定几何关系 | 独立测量状态、行为动力学范围和与 AD 决策相关的 margin |
| HUGSIM ego/actor state 与 NC/TTC/PDMS | 仿真器声明状态及其内部 AD-performance score | 完全依赖 HUGSIM 状态、地图、计划与 scorer；已审出尾窗填充和 TTC 构念边界 | 内部状态/评分诊断，不作现实裁判 | 完整未来时域内的 HUGSIM 内部状态和二值 planned-path TTC surrogate | 独立状态/结果、物理 TTC 或受控场地对照 |
| HUGSIM RGB / semantic / depth 与边界共变 | 渲染像素、声明语义/深度和跨模态内部对齐 | 三种模态共享 HUGSIM renderer，无独立现实参考 | 仅作可见性、错位和 artifact 定位 | 模态是否在 HUGSIM 内部共同变化 | 匹配或独立 RGB、depth/lidar、语义标注和误差范围 |
| COCO detector 与 center-path risk proxy | 通用 2D 类别响应及人工加权图像风险 | detector 有外部 COCO 训练基础，但非驾驶域；risk proxy 未校准且已被 nuisance 主导 | nuisance 诊断；不进入下一反事实裁决 | 背景/重建内容能否诱发通用检测响应 | 驾驶域真实数据、独立任务标签和 risk/action calibration |
| 冻结 Sparse4Dv3 序数关系响应 | 六相机 RGB 下的车辆存在、near/far、same/adjacent 和短时跟踪 | 官方 real-nuScenes-trained receiver，不读取 HUGSIM semantic/depth；真实 benchmark 能力为官方报告，尚未在本项目独立复核，HUGSIM 标定/域差仍存在 | 可作为一个 supporting receiver probe，限序数方向 | 在已测 receiver contract 中，HUGSIM RGB 能驱动该接收方产生预期关系方向 | matched/独立 3D 参考、第二个不同失败模式接收方、task margin 和 receiver uncertainty |
| 固定人眼可见性标注 | 检测响应在渲染 RGB 中是否有可见目标支撑 | 人工判断独立于 HUGSIM semantic/depth/state，但仍只观察 HUGSIM RGB，且仅一次小样本复核 | 固定样本 nuisance 审计，不作现实语义真值 | 14 个固定响应中 7 个有可见支撑、7 个为 nuisance | 真实或独立场景标注、完整目标清单、多复核者和 recall 设计 |
| Cross-receiver agreement | 不同输出构造的干预排序方向是否一致 | 当前接收方共享 HUGSIM 输入，部分还依赖 HUGSIM semantic/depth，误差相关性未量化 | 内部收敛诊断，不作多数投票 | 当前少量条件中的 effect-direction convergence | 各接收方真实数据资格、依赖性审计、独立参考和不确定性 |
| Task acceptance boundary / uncertainty envelope | 哪些误差会改变关键目标、风险排序或动作 | 当前没有冻结的外部任务 margin，也没有合理参数/模型不确定性范围 | 当前不可用；是 designed counterfactual 分支的阻塞缺口 | 不能给出任务适用性通过结论 | 外部可辩护的任务构念、margin、参数范围和结论稳定性规则 |

资格判断的直接依据为：

- source/pairing：`docs/runs/hugsim_source_anchor_gate_001.md`；
- horizon、几何与 scorer：`docs/runs/hugsim_horizon_factorial_001.md`、
  `docs/runs/hugsim_near_cut_in_001.md`；
- sensor/proxy/nuisance：`docs/runs/hugsim_normal_scene_sensor_audit_001.md`、
  `docs/runs/hugsim_camera_detector_001.md`；
- receiver 与依赖关系：`docs/runs/hugsim_sparse4d_receiver_baseline_001.md`、
  `docs/runs/hugsim_sparse4d_cross_scene_001.md`、
  `docs/runs/hugsim_receiver_agreement_001.md`；
- 人眼固定样本：`docs/runs/hugsim_sparse4d_normal_scene_annotation_001.md`。

### 资格结论

当前保留两个有限用途候选：

1. **时域有效性 + 独立二维几何/因果约束套件**，用于确认反事实干预本身在
   HUGSIM 声明状态下有效；
2. **冻结 Sparse4Dv3 的序数关系响应**，作为一个 real-data-trained supporting
   receiver probe，不作为真值或唯一裁判。

这两类工具合起来最多回答：“干预是否按声明发生，以及一个冻结驾驶域接收方
是否沿预期序数方向响应。”它们不能回答“HUGSIM 是否足以作为 AD 测试域”。

直接 matched real-sim 分支仍被 source gate 阻断。Designed-counterfactual
分支可以作为下一准备方向，但现在不应立即跑新场景；最小缺口是先为一个任务
结论建立外部可辩护的 acceptance boundary 和 uncertainty envelope。若该结论在
合理范围内不稳定，就不能用单次 HUGSIM 结果作可信判断。

## 12. 任务边界资格审计 001 — 关键目标与风险排序

本轮不把“关键目标”定义为某个检测器最高置信度的框，也不把 HUGSIM 的 TTC
或 PDMS 当成危险真值。外部方法依据只支持以下更窄的任务构念：在一个声明的
自车候选走廊和有限未来时域内，比较各 actor 与走廊的空间冲突关系，并检查
**关键目标身份和风险序数关系**在合理变化下是否稳定。

这一限定来自三类外部依据：

- [ISO 34502:2022](https://www.iso.org/standard/78951.html)给出面向 ADS 的场景化
  安全评价框架，但适用范围和场景必须明确；它不是跨 ODD 的通用危险阈值表；
- [Criticality Metrics for Automated Driving](https://elib.dlr.de/187762/1/Westhofen2022_Article_CriticalityMetricsForAutomated.pdf)
  明确把 pass/fail target value 绑定到上位安全目标，并指出指标有效性依赖场景
  类型和所用 future-prediction model；
- [RSS formal model](https://arxiv.org/abs/1708.06374)说明纵向、横向、交叉路线和
  遮挡风险可以用显式几何、运动界和响应假设形成可检查约束；它提供构造方法，
  但反应时间、加减速度等参数仍须针对被测系统和 ODD 声明。

### 冻结的任务构念

对每个 actor 和每个声明的未来假设，保留两个不合成为单一分数的基本关系：

1. actor footprint 是否进入或穿越自车候选走廊，以及首次冲突的先后；
2. actor footprint 到自车/候选走廊的最小正净距及其变化方向。

只在 actor A 对所有声明假设都不比 actor B 更安全，并在至少一个关系上更危险
时，写作 `A > B`。若不同未来假设、不同几何关系或接收方可见性给出相反排序，
结果必须写成 **unresolved partial order**，不能靠加权平均强行产生唯一冠军。
Sparse4Dv3 只检查“接收方是否仍得到该 actor 及其序数关系”，不决定几何风险
真值；HUGSIM semantic、depth、NC、TTC 和 PDMS 也不参与外部裁决。

### 当前 acceptance boundary

本轮能够冻结的不是“几米/几秒即危险”，而是一个序数稳健性边界：

- 运行身份、输入和完整未来时域 gate 必须通过；
- 每个离散干预必须由独立二维 footprint/净距重算确认其声明关系；
- 距离减小、进入自车走廊或冲突时间提前时，关键目标身份/排序不得在没有明确
  遮挡或可见性原因的情况下向更安全方向反转；
- 在声明的几何、运动、渲染 nuisance 和 receiver 变化集合中，关键目标身份与
  偏序保持不反转，才可报告“该序数结论在此设计范围内稳健”；
- 任何反转都保留为边界/失效证据，不用多数投票覆盖。

该边界允许的最强主张是：**某项受控干预在 HUGSIM 声明状态下满足几何约束，
且一个冻结驾驶域接收方得到的关键目标/风险方向在声明的设计变化内不反转。**
它不允许写成现实碰撞概率、真实 AD 安全/危险判定、real-sim 等效，或 HUGSIM
已经适合作为一般 AD 测试域。

### 资格结果与剩余缺口

任务构念和定性 acceptance rule 已获外部方法支撑，可以进入实验设计；**数值
uncertainty envelope 尚未获资格**。仓库目前没有可独立支撑以下范围的数据：

| 不确定性维度 | 下一实验必须声明的量 | 当前状态 |
|---|---|---|
| 几何 | box/位姿/标定误差和车道/走廊边界误差 | 无独立 3D 真值或 matched source，未资格化 |
| 运动 | 速度、加速度、制动能力、反应时间和多未来轨迹 | 无目标 AD/ODD 合同，未资格化 |
| 渲染 nuisance | 光照、模糊、遮挡和重建 artifact 的合理变化范围 | 无 matched real 分布，未资格化 |
| receiver | 检测/跟踪波动、漏检范围和模型间差异 | 只有一个冻结 Sparse4Dv3，未资格化 |

因此下一步不能直接设一个“真实风险阈值”。可以先做**设计范围内的序数形变
测试**：预注册若干离散、可复算的干预级别，只裁决风险方向是否反转；这些级别
必须明确标为 test-design coverage，不能冒充现实分布。要把结论升级为 AD 测试
域适用性，仍需目标 AD/ODD 合同、独立状态参考或真实数据统计来资格化上述范围。

该测试已经预注册为
`docs/runs/hugsim_ordinal_metamorphic_preregistration_001.md` 及同名 JSON。
它固定 `scene-0383`、一个车辆资产、无 actor 基线和纵向×横向 2×2 矩阵；遮挡
因缺少无混杂操纵在 001 中明确排除。发布时状态为 `preregistered_not_run`；执行
结果记录在下一节。

## 13. 序数形变审计 001 结果

预注册随后在提交 `c784cbcdd6c3ff4554a26e79d683bcf8703b42b1` 固定后按清单
运行。五个条件均完成 36/36 steps；严格配对和完整未来时域 gate 通过。结果见
`docs/runs/hugsim_ordinal_metamorphic_001.md`。

| 预声明关系 | 独立几何 | Sparse4Dv3 expected / reversal / unavailable | 裁决 |
|---|---:|---:|---|
| centre/near > centre/far | 26/26 | 13 / 0 / 0 | `accepted` |
| centre/near > adjacent/near | 26/26 | 12 / 0 / 1 | `down-weighted` |
| centre/far > adjacent/far | 26/26 | 13 / 0 / 0 | `accepted` |
| adjacent/near > adjacent/far | 26/26 | 12 / 0 / 1 | `down-weighted` |

四条几何关系均逐帧成立，所有可用 receiver 对比都沿预期方向，未出现反转。
两条关系因 `adjacent_near@6.5s` 同一个 association 缺失而 down-weighted；“所有
关系在所有 receiver 时刻完整可用”的具体主张被 rejected。原因尚未在渲染、
标定/domain shift 与 receiver 之间隔离，因此不归因为 HUGSIM 单方失败。

这一实验说明资格化后的大方向手段确实能工作：HUGSIM 内部 NC/TTC/PDMS 在有效
窗口对五个条件都为 1.0，而独立几何 + 冻结 receiver 的序数关系能区分纵向和
横向任务变化。但它仍只是 design-range causal/ordinal positive evidence；数值
范围没有现实资格，接收方只有一个，不能升级为 AD 测试域适用性结论。

下一步停止增加 HUGSIM 条件，先资格化一个外部 uncertainty axis。优先选择
receiver 外部效度：审计 Sparse4Dv3 在真实 nuScenes 上可独立支持哪些检测/跟踪
构念、误差和适用范围；若官方/公开证据不能给出本任务所需边界，就明确记录需要
的最小真实标注或第二接收方证据，不从本次 HUGSIM 结果反推阈值。

> 方向更新（2026-07-22）：上述是本次实验完成时的后续建议，现已后移。当前先按
> `docs/counterfactual_credibility_constraints.md` 完成反事实规律与可证伪骨架；
> Sparse4Dv3 外部资格审计留到接收方实验阶段。
