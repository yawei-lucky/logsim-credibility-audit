# HUGSIM CF-O 001 可控遮挡实验结果

## 结论

六个条件均按预注册提交 `4b9bcd4` 完成 36/36 step，运行版本、配置、ego
状态/动作/计划和 plan-writer 契约通过配对检查。actor 身份与保存状态完全配对，
声明的纵向/横向偏移无残差，两个 actor 的最小 footprint 净距为 0.424 m。

但 001 **不能接受相机投影与 RGB 可见性主张**。原分析器把 HUGSIM 保存 box 的
第三坐标符号解释反了，投影掩码位于真实车辆下方，导致 37/37 帧参考支撑均为
0 像素并被标为 `unavailable`。因此：

- 世界状态干预与配对完整性：`accepted`；
- 001 的相机投影测量有效性：`rejected`；
- 001 的目标 RGB 支撑单调主张：`rejected`（未被有效测试，不代表 HUGSIM
  可见性能力失败）；
- 整体 segment：`rejected`，拒绝的是 001 测量链，不是 HUGSIM 的遮挡能力。

## 诊断依据

`target_only - no_actor` 在完整 `CAM_FRONT` 中每帧实际存在 1,641–3,883 个
`RGB max-channel difference > 10` 的像素，目标确实被渲染；但原投影掩码与这些
像素零交集。首/中/末帧中，实际差分分别位于约 `y=218–256`、`214–260`、
`205–265`，原掩码却位于 `y=292–331`、`302–351`、`318–385`。

HUGSIM `objs_list` 将渲染器竖直坐标取负后保存到 box 第三维；转换回 vehicle
frame 应使用 `z_vehicle = z_ego - z_actor`。001 使用了相反方向。这是已定位、
可单测的分析器错误，而不是靠改变实验阈值得出的解释。

## 产物与后续

原始运行位于：

```text
artifacts/hugsim_occlusion_metamorphic/*-run001
```

原始分析位于：

```text
artifacts/hugsim_occlusion_metamorphic/analysis-run001
```

这些产物保留，不覆盖。CF-O 002 只修正坐标符号、保持所有干预和裁决阈值不变，
并使用全新的 `run002` 目录进行纠错复验。002 即使通过也不是独立场景证据。
