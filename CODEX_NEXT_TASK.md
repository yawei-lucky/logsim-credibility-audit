# Codex Next Task — 冻结 SparseDrive 发布回归

> 顶层：**预测结构一致性、动作效应一致性、任务边界一致性**。
> 当前重点：解释误差经什么过程传播，以及何时不可忽略；不以通过项数量背书。
> 主方法见 [CREDIBILITY_VALIDATION_METHOD.md](CREDIBILITY_VALIDATION_METHOD.md)。

## 最新已完成（2026-10-11）

用户要求参考 NVIDIA／理想 NuRec 的验证做法继续实际实验。本轮继
[HUGSIM 运动成像标靶实验 001](docs/runs/motion_observation_probe_001.md) 后，完成了
[运动成像适用边界实验 001](docs/runs/motion_observation_boundary_001.md)。

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

## 下一项：NuRec 式冻结接收方回归

1. 把完整 `run002` 的 straight 与 turn 窗口分别无损装配为 receiver-ready 输入；
   两段必须独立 reset，不能合为一条 16 帧历史。
2. 保持 SparseDrive commit/working diff、Stage2 checkpoint、config、adapter、
   calibration、相机顺序和预处理不变；每段运行 baseline 与 independent reset
   repeat，共 32 次 frame forward。
3. 逐帧比较 historical-sim 与 current-sim 的 selected mode、六个 final waypoints
   和完整 native tensor 结构；final-plan 主门沿用已冻结 receiver tolerance
   `1e-4 m`，整数输出必须精确相同，并报告相对本地 reset envelope 的幅度。
4. 真实 RGB 不重跑；若接收方回归通过，复用已有 real report 检查旧的
   `D_domain` 数值是否由当前 sim receiver 输出保持。该实验只裁决发布回归和
   runtime 复现性，不新增现实等效证据。

不把当前零散场景合成为“事件复现率”；仓库没有 NuRec 式同类真实事件簇和合格
抽样分布。先完成上述固定窗口回归，再决定是否有信息增益继续接收方重跑。

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
