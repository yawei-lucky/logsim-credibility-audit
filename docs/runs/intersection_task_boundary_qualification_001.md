# 交叉口任务边界资格审计 001

日期：2026-09-01

机器记录：`docs/runs/intersection_task_boundary_qualification_001.json`

## 1. 结论先行

当前任务边界可以通过，但只通过到**来源独立的几何零边界与序数实验**：

> 在固定的公共 ego 路径和相交/对向 actor 路径上，用双方车辆 footprint 对同一冲突区
> 的占用时间关系，判断设计刺激是分时、临界还是重叠；再检查固定 SparseDrive 的
> 原生计划是否减轻该冲突。

“占用是否重叠”的零点来自集合与时间区间关系，不从 HUGSIM 输出、SparseDrive
结果或期望通过的结论倒推，因此可用于前瞻实验。它不是现实安全距离或事故概率
阈值。整体资格仍为 `down-weighted`：缺少车道级独立地图、现实安全余量、源 RGB
和 SparseDrive 原生关键目标身份。

任务边界 gate 的结果是：`accepted`（仅限序数/几何边界）。下一项实验可以做，
但不得写成现实安全、真实—仿真等效或 HUGSIM 普遍可信验证。

## 2. 冻结 claim card

| 字段 | 本轮冻结内容 |
|---|---|
| `S` | HUGSIM commit `adeca402cad4af8635e13d0a105e2fee6a14de85`；`scene-0041` archive SHA-256 `8d066a3594ad5dc0f43944cff7ec1a5aa364011792236551e4802c483d0550fe`；现有六相机接口 |
| `T` | 检查仿真器是否保留转弯末段对向路径冲突的序数关系，并把这种差异传给目标 AD 的规划输出 |
| `Ω` | `scene-0041` 白天单交叉口；一个脚本对向 actor；固定参考相机轨迹；完整 3 s 规划未来；单一 command 上下文 |
| `A` | SparseDrive-S Stage2，source commit `ec0225d4b7a2dd7e6ce10179a2b7660dcb74b2f1`，checkpoint SHA-256 `a9786bd3398907666ef436b287b465d6de8c424467413648e4614e0b884db7ad`；它是被测 AD，不是真值 |
| `I` | 只改变同一 actor 到达固定冲突区的相位；资产、尺寸、路径、姿态、相机位姿、ego 历史、command、时间原点和渲染配置保持不变 |
| `Y` | 公共 ego 路径的有符号占用时间净距；SparseDrive 计划相对公共路径的冲突变化；selected mode 与固定 mode 分解 |
| `Θ` | 独立 reset 重复，以及预先冻结的少量到达相位/横向位置网格；只能解释为人工设计网格 |
| `ε` | `0 s` 占用重叠边界；本地 repeat envelope 只判定数值响应是否可分辨。现实安全余量仍未资格化 |
| `R` | 时间区间/footprint 集合关系与外部冲突构念；世界状态仍来自 HUGSIM，因此只有计算独立，没有完整来源独立 |
| `Req` | 本轮 open-loop 主张要求 `G + Q + U + O_plan`；不要求 `F`，也不暗示闭环 `O` 已通过 |

## 3. 边界定义

令固定冲突区为 `C`。ego 公共路径与 actor 路径的 footprint 分别占用 `C` 的
时间区间为：

$$
T_e=[t^{e}_{in},t^{e}_{out}],\qquad
T_a=[t^{a}_{in},t^{a}_{out}]
$$

定义有符号占用时间净距：

$$
c=\max(t^{e}_{in},t^{a}_{in})-
  \min(t^{e}_{out},t^{a}_{out})
$$

- `c > 0`：双方分时占用冲突区；
- `c = 0`：占用区间刚好相接；
- `c < 0`：占用时间重叠；
- 在其他量冻结时，更小的 `c` 是更强的设计冲突。

该公式只在 ego 和 actor 对 `C` 都有一个连续、非空且未被分析时域截断的占用区间
时直接成立。正式注册前还必须冻结以下分支：plan 空间避开 `C`、只在 3 s 时域后
进入 `C`、多次进入/离开 `C` 以及区间被窗口边界截断；这些情况不能临时塞入一个
有限 `c` 数值。

这与交通冲突研究中按同一冲突位置/区域的先后占用来定义 PET 的构念一致；本项目
把重叠部分扩展为负值时，名称固定为“有符号占用时间净距”，不冒充标准 PET。
[FHWA SSAM 报告](https://highways.dot.gov/sites/fhwa.dot.gov/files/FHWA-HRT-08-051.pdf)
给出了 PET 构念；RSS 也用相交路线及车辆到达交叉区的时间区间描述交叉口安全
关系。[RSS 原始论文](https://arxiv.org/abs/1708.06374)

本边界只给出必要的几何/时序关系。已有综述指出，TTC/PET 等指标的适用性取决于
场景、预测模型和用途，因此这里不自行设置“几秒以内危险”的现实阈值。
[DLR criticality-metric review](https://elib.dlr.de/187762/1/Westhofen2022_Article_CriticalityMetricsForAutomated.pdf)

## 4. 规划后果怎样判断

交叉口响应不能预设为“越危险越少向前”。减速让行、提前通过或空间绕开都可能
减轻冲突。因此对 SparseDrive 的每条原生候选计划，重新计算同一个 `c` 或明确
记录其在 3 s 时域内避开冲突区；最终计划相对公共非响应路径：

- 增大 `c`、消除负重叠或空间避开冲突区：冲突减轻；
- `c` 无变化：未观察到该构念上的减轻；
- 减小 `c` 或由分时变成重叠：方向反转。

同时报告 selected mode 和六个固定 mode 的分解。模式编号不能事后命名为
“跟车”“转弯”等行为。只有响应大于本地 repeat 和时间离散误差时，才能说
“接收方产生了可分辨响应”；这仍不说明幅度符合现实。

SparseDrive 发布输出没有经过资格化的 `critical_object_id` 或校准风险排序，故
本轮删除“AD 把注入车排为第一危险目标”的主张。最多称该 actor 是公共路径上的
**几何关键 actor**，并检查其可见输入是否引起规划变化。

## 5. 为什么选 scene-0041，以及发现的执行混杂

`scene-0041` 没有参与 Method Qualification 001 的 challenge set，且相较此前的
同车道 lead-actor 场景增加了新的交叉口、对向路径和转弯几何，因此可以作为冻结
规则后的前瞻 challenge。ISO 34505 将测试目标、输入、步骤、平台、预期结果和
覆盖准则作为场景测试用例要素；本轮据此先固定任务后果和预期关系，再看结果。
[ISO 34505:2025](https://www.iso.org/standard/78954.html)

但现有证据暴露了不能忽略的路线混杂：

- released 参考相机路线长约 `110.082 m`，净航向变化约 `-86.246°`；
- command 在弧长约 `9.979 m` 由 `2` 变为 `1`，在约 `39.585 m` 再变为 `2`；
- 现有 9 s normal rollout 没有执行这条左转路线，而是始终 `yaw=0` 直行
  `17.510 m`，command 又在 `5.25 s` 附近切换；
- 因而旧 rollout 不合格为“日志左转事实基线”，跨 command 的规划差异也不能
  归因于注入 actor。

正式实验优先固定 metadata 的参考相机位姿/时间做 open-loop 渲染。若以后仍用旧
直行 rollout，主张必须改称“交叉口背景中的直行公共走廊刺激”，且在单一 command
内分层分析。

## 6. 场景执行资格与前置 setup

本地 ground 支撑显示宽路面大致位于局部 forward `b=28–32 m`；但本地没有
可用 HD map，不能从当前资料确认精确车道中心、法定行驶方向或交通优先权。因此
不能直接把某个坐标冻结成“真实对向/交叉车道”。

下一步先做一次明确排除在正式裁决之外的 geometry placement setup：

1. 固定一小段参考 ego 位姿和单一 command；
2. 在 `b=28–32 m` 内枚举少量静态 actor 候选位置；
3. 检查六相机 RGB 支撑、ground 高度、box 尺度/朝向、背景穿透及可用时域；
4. 只根据这些执行 gate 选定冲突区和路径，不查看 SparseDrive 规划结果；
5. 冻结分时、临界、重叠三档到达相位后，再注册正式实验。

actor 固定使用 RealCar `2024_07_05_15_57_10`，尺寸约
`1.625 × 3.576 × 1.175 m`，`gs.pth` SHA-256
`3d8b314a9c2ae521464f3973edb4122958f8b580e4168bd6047fc0186094d006`。
普通 HUGSIM env 的 `ConstantPlanner` 只提供直线脚本运动，且 reset 会在第一个
timestamp-zero observation 前推进一次 `0.25 s`。当前优先的 exact-pose metadata
路径不调用该 reset，而是按 metadata timestamp 显式写入 actor transform；正式
manifest 必须记录使用的是哪一种相位合同，二者不能混用。

## 7. 预注册裁决规则

| 子主张 | 必要证据 | 通过条件 | 当前边界状态 |
|---|---|---|---|
| 干预按声明发生 | `G` | 身份、坐标、连续 actor future、reset 相位、ego/相机/command 配对全部通过 | `accepted` 为规则；待正式运行 |
| 三档刺激顺序成立 | `G + Q` | 公共路径上 `c_separated > c_boundary > c_overlap`，无尾窗填充 | `accepted` 的序数边界；待正式运行 |
| actor 到达 AD 输入 | `G` | 声明 actor 在相关相机有可核验 RGB 支撑；不能以 HUGSIM semantic/depth 自证 | `accepted` 为必要 gate；待正式运行 |
| SparseDrive 有可分辨响应 | `Q + U` | 原生计划差异超过独立 reset 与时间离散误差 | `down-weighted`，只判响应存在 |
| 规划响应减轻冲突 | `Q + U + O_plan` | 在同 command/可比模式内，正式网格无无解释反转；报告 `k/n` 与最小裕量 | `down-weighted`，无现实幅度资格 |
| 现实安全阈值或事故概率 | `F + U + O_real` | 当前没有来源独立数值边界和现实结果 | `rejected`（本实验范围外） |
| AD 内部关键目标排名 | 原生身份/风险输出 | SparseDrive 当前接口不提供合格输出 | `rejected`（本实验范围外） |

任何硬 gate 失败都拒绝对应正式主张。人工 `Θ` 网格只报告 `k/n` 次不反转；不写
现实概率或置信区间。虚拟测试环境的资格应针对预期用途、接口和闭环/开环范围，
不能由单项输出替代；ISO/PAS 34506 的公开范围也明确区分测试环境资格与具体 ADS
评价。[ISO/PAS 34506](https://www.iso.org/standard/89865.html)

## 8. 最强允许结论

若前瞻实验全部通过，最多可以写：

> 在 `scene-0041` 的指定参考位姿窗口、公共路径和人工到达相位网格内，HUGSIM
> 记录状态保留了预注册的对向路径占用顺序，且固定 SparseDrive 对可见注入车辆产生了
> 超过局部重复误差、方向可解释的冲突减轻响应。

仍不能支持：现实安全阈值、AD 内部危险目标排名、响应幅度真实性、matched
real–sim 等效、闭环安全或 HUGSIM 普遍可信。
