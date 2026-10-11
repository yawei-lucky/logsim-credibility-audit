# Codex Next Task — 从冻结回归转向外部任务边界

> 顶层：**预测结构一致性、动作效应一致性、任务边界一致性**。
> 当前重点：解释误差经什么过程传播，以及何时不可忽略；不以通过项数量背书。
> 主方法见 [CREDIBILITY_VALIDATION_METHOD.md](CREDIBILITY_VALIDATION_METHOD.md)。

## 最新已完成（2026-10-11）

用户要求参考 NVIDIA／理想 NuRec 的验证做法继续实际实验。本轮已完成三组互相
衔接的实验：运动成像适用边界、冻结轨迹渲染回归、冻结 SparseDrive 接收方回归，
并在主回归失败后完成一个全新进程诊断。

[运动成像适用边界实验 001](docs/runs/motion_observation_boundary_001.md)：

- 750 个 CPU 资格图对最大宽度误差 0.027223 px，低于冻结的 0.5 px 预算。
- 两背景、三深度中 36/36 个可见图对符合完整三维端点投影，最大残差
  0.035443 px。
- 转动／非等深的 24/24 图对排除 `fxW/Z_center`；端点深度不同的 18/18 图对
  进一步排除共同深度近似，明确了简化模型边界。
- 遮挡体后置 6/6 仍可测；前置和显式缺失各 6/6 精确返回一个分量，不补造宽度；
  临时 opacity 恢复 6/6 逐像素一致。
- 两个成功独立进程的 108/108 张 PNG 哈希及 48/48 个测量记录完全一致。
- 另保留两个失败运行：一次结果序列化缺陷已窄修复；一次 PyTorch／SymPy 启动
  异常尚未隔离，提醒后续保留进程健康门。

完整投影、模型前提诊断和受控不可测行为在有限网格内为 `accepted`；简化公式的
超范围主张为 `rejected`；整体仍为 `down-weighted`。普通车辆、现实遮挡、真实
相机和 AD 没有因此获得资格。

随后完成 [HUGSIM 冻结轨迹渲染回归 001](docs/runs/fixed_trajectory_render_regression_001.md)：

- 两个完整成功轮次的 96/96 张 RGB 逐字节、逐像素相同，且两轮各自与历史
  golden 96/96 相同；最大像素差 0、最小 SSIM 1.0。
- 第一轮一个 frame 66 子进程在 0.214 s 后以 `SIGSEGV` 退出；预注册两轮合计
  31/32 进程完成，所以 32/32 启动完整性及原两轮完整比较主张为 `rejected`。
- outcome-informed 第三轮 16/16 完成，只支持成功轮次的窄 RGB 重复性，不抹掉
  原失败；故障组件未隔离。
- 窄 RGB 历史兼容性为 `accepted`，运行机制诊断和整体 segment 均为
  `down-weighted`；没有因此建立现实等效。

[冻结轨迹 SparseDrive 接收方回归 001](docs/runs/fixed_trajectory_receiver_regression_001.md)
及其[全新进程诊断](docs/runs/fixed_trajectory_receiver_process_repeat_001.md)：

- 96 张输入与历史 golden 逐字节相同；historical↔current 的 32/32 个
  mode/command 相同，final plan 最大差 `2.003e-5 m`；已有 `D_domain` 最大重算
  差 `1.767e-5 m`。这些窄发布回归均低于冻结的 `1e-4 m` 门。
- 完整 native historical↔current 主门失败：float 最大差 `66.6675`，22 个
  integer mismatch；ID 对齐后轨迹差仍达 `0.03824`。
- 在预注册 commit `9e61dcb` 后又执行 current run002↔run003 全新进程比较。
  32/32 个 mode/command 仍相同，final plan 最大差 `2.098e-5 m`；完整 native
  仍有最大 float 差 `66.6675` 和 24 个 integer mismatch，ID 对齐后轨迹差
  `0.05235`。
- 因而 final-plan 容差回归可在两个冻结窗口内 `accepted`；完整 native 逐元素
  golden 主张为 `rejected`；内部变化触发机制和整体证据仍为 `down-weighted`。
  全新进程结果说明历史 release drift 不是唯一充分解释，但没有定位具体组件。

## 当前下一步

停止增加同一输入的普通重复运行，也不事后放宽 native 阈值。下一项有信息增益的
工作必须改变独立证据来源或资格化任务边界：

1. 若目标是把仿真用于最终规划回归，先从目标 AD／ODD 或独立真实统计取得可辩护
   的 plan/task margin，再检验 real–sim 差异是否会跨越该边界；当前 `1e-4 m`
   只是数值回归容差，不是驾驶安全阈值。
2. 若目标依赖检测、box 或 trajectory 中间量，预注册字段级匹配规则、任务容许
   误差和低分输出处理，再用独立标注或 matched real reference 裁决；不能由
   final-plan 稳定性替代。
3. 若要做 NuRec 式事件复现率，需要同类真实事件簇、冻结事件定义和合格抽样
   分母。当前零散场景不能合成为“复现率”。

在这些外部输入出现前，最可靠的现有用途是两个窗口上的冻结 RGB identity 与
SparseDrive final-plan 容差回归；它不是 HUGSIM 现实等效或整体可信的证明。

## 前序理论工作（2026-09-25）

详见[运动—成像误差传播样板 001](docs/motion_observation_mechanism_001.md)。

- 核查经典视觉运动理论、工业工具说明及传感器模型验证工作：基础关系已有，
  不能当作创新，也不能据公开资料推测车厂内部量产流程。
- 写出距离偏差、时间偏差和比例变化到图像相对增长率的传播关系、条件误差界，
  以及单速度下距离偏差／延迟不可分、两速度下条件可分的设计依据。
- 明确有限窗测量及其误差界，区分采集状态正确性与交付时刻信息年龄。
- 只读核查相关 CF-M、CF-I-OBS 记录与产物路径；旧状态／图像可复用，但物体框
  和 Gaussian 中心包络不能直接升级为独立的 RGB 轮廓真值。

以上是**文献、推导及方案**，不是新 HUGSIM、AD 或实车实验；旧裁决均保留。

## 前序测量资格计划的处理

短窗口筛查、独立标靶资格化、冻结配置和机制比较已由本轮实验落实。
旧车辆特征的物理宽度资格仍未建立；没有用新学习模型补真值。10 月 11 日的
用户实验授权替代了此前“此步先定配置”的执行边界。

继续同时检查绝对投影与动态变化，不能因增长率一致而忽略尺度偏差或误差抵消。
没有独立任务容许误差前，只报告条件误差界，不宣布驾驶安全或整体仿真可信。

## 暂缓与保留

- SparseDrive 输入缺失／陈旧时序实验按用户确认暂缓；原五步方案保留于
  Git `4f0d982:CODEX_NEXT_TASK.md`，不是已经执行的实验。
- [停车指标盲区 001](docs/runs/stopping_metric_blindspot_001.md) 的参考系统结果保留；
  不将两帧确认、常制动合同搬到 SparseDrive 或 HUGSIM。
- compact-conflict task compatibility 002 的 geometry-only 待办暂缓，未执行；
  原方案保留于 Git `ecf031c:CODEX_NEXT_TASK.md`。
- scene-0041 opposing-path 的几何/传输正面证据和任务时域不足保留原裁决，
  不因本轮方法更新翻案。
- 不更换 HUGSIM，不引入 AD 或学习型验证器，不扩场景；四层仅作证据归档。
