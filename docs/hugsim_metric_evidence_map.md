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
| Planning | 目标轨迹、go/slow/stop、风险排序 | 目标 AD planner，尚未接入 | AD 决策输出 | 尚未形成当前证据 | 任何规划一致性主张 | 同一冻结 AD 的匹配真实—仿真输入和输出 |
| Control / outcome | brake、steer、干预时间、碰撞和任务结果 | 目标 AD/controller，尚未接入 | 控制行为和闭环结果 | 尚未形成当前证据 | 真实车辆闭环可信性 | 匹配闭环参照、车辆动力学和不确定性范围 |

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
3. 选择少量能够回答大方向问题的指标，明确独立参考和允许主张；
4. 在源数据可用时，使用同一冻结 AD 接收方做匹配真实—仿真比较；
5. factual 比较成立后，再进行距离、车道、遮挡和运动反事实；
6. 最后进入 planning、control 和闭环结果，不用 perception proxy 提前替代它们。

当前已有 proxy、detector 和 cross-receiver 曲线保留为指标审计材料，不作为 HUGSIM 可信性的最终结果。

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
