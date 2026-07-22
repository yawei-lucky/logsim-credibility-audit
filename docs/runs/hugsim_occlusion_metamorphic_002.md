# HUGSIM CF-O 002 可控遮挡纠错复验结果

## 结论

CF-O 002 按提交 `a0d44bf` 中的纠错预注册执行完成。六个条件均完成 36/36
step，运行版本、配置、ego 状态/动作/计划和 plan-writer 契约通过 fail-closed
检查。run002 与 run001 的六条件 RGB 逐像素最大差为 0，ego 状态最大差为 0；
原始仿真完全复现，变化只来自预声明的 box 高度符号修复。

两个窄主张均为 `accepted`：

1. 当前 target/occluder 的保存状态、深度顺序、footprint 净距和 CAM_FRONT box
   投影满足预声明的遮挡几何；
2. 37/37 个有效帧中，strong 条件的目标配对 RGB 支撑均不高于 partial，且窗口
   中位数严格下降，没有反转、缺测或背景控制带漂移。

整体 segment 仍为 `down-weighted`：这是同一场景在发现 001 测量缺陷后的纠错
复验，并且 box、标定和 RGB 全部来自 HUGSIM。它不是独立现实真值或独立场景
样本。

本次实验只验证“基本可见—完全遮挡”的明显端点规律，不代表连续遮挡曲线、
真实传感器一致性或 AD 响应可信。

## 几何入口结果

| 检查 | 结果 |
|---|---:|
| 角色状态跨因子条件最大差 | 0 |
| 声明平面偏移最大残差 | 0 m |
| 两 actor 最小 footprint 净距 | 0.424 m |
| 几何有效帧 | 37/37 |
| partial 目标 box 覆盖率 | 0.430–0.441；中位 0.437 |
| strong 目标 box 覆盖率 | 1.000（全窗口） |
| partial-only 非嵌套像素 | 0 |

这些数值是独立代码根据 HUGSIM 保存 box 和标定重算的投影代理，不是真实可见
表面的外部标注。

## 目标配对 RGB 支撑

六条件因子差分把目标贡献与遮挡车自身贡献分开。每帧无遮挡参考支撑为
903–1,889 个像素，全部高于 25 像素资格门槛。

| 指标 | partial | strong |
|---|---:|---:|
| 支撑率最小值 | 1.000 | 0.000 |
| 支撑率中位数 | 1.000 | 0.000 |
| 支撑率最大值 | 1.000 | 0.0022 |

37/37 帧方向成立，0 反转、0 缺测；顶部背景控制带变化率始终为 0。画面也与
指标一致：偏置车辆位于目标右侧，目标仍完整可辨；居中车辆位于更近深度并几乎
完全遮住目标。

这里没有证明“44% box 覆盖会造成 44% 视觉信息损失”。恰恰相反，partial 的
box 凸包虽然与目标凸包重叠约 44%，目标自身的显著 RGB 支撑仍为 1.0，说明 box
覆盖只是粗几何代理。CF-O 002 验证的是明显的两端方向，不是连续、定量准确的
遮挡响应曲线。

## 可视化与机器结果

```text
artifacts/hugsim_occlusion_metamorphic/analysis-run002/occlusion_indicator_summary.png
artifacts/hugsim_occlusion_metamorphic/analysis-run002/occlusion_cam_front_contact_sheet.png
artifacts/hugsim_occlusion_metamorphic/analysis-run002/occlusion_cam_front_comparison.mp4
artifacts/hugsim_occlusion_metamorphic/analysis-run002/occlusion_metamorphic_audit.json
```

图中标题沿用原套件名 `CF-O 001`，实际数据目录和预注册提交均为纠错复验 002；
该显示文字不参与裁决。

## 对研究的推动

CF-O 建立了一种不依赖 detector confidence、HUGSIM semantic/depth 或内置评分器
的可见性审计方法：先保证世界状态和投影关系，再用六条件配对差分测目标自身的
RGB 因果贡献，同时把缺测和背景漂移排除在通过之外。

它提供了一条窄正面证据，也保留了一条负面方法证据：001 暴露坐标约定错误，
002 证明修复后指标能识别明显遮挡方向。下一种互补机制应进入 CF-I 交互能力，
而不是继续在本场景调出更平滑的遮挡曲线。
