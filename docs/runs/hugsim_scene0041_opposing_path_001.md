# HUGSIM scene-0041 对向路径实验 001

日期：2026-09-05

机器记录：`docs/runs/hugsim_scene0041_opposing_path_001.json`

预注册提交：`c9dba9c`

## 结论先行

这是第一个在新场景 `scene-0041` 上完成“几何刺激 → 六相机 RGB → 固定
SparseDrive”的预注册实验。结果不是简单通过：

- 三档干预和 RGB 传输合同通过；
- SparseDrive 确实产生了远大于重复误差的响应；
- 但响应不满足简单的风险—减速单调关系；
- 更关键的是，近对向路径形成的冲突区太长，SparseDrive 固定 3 s 计划在窗口末端仍
  未离开冲突区，触发预注册的截断/多区间规则，主指标必须返回 `null`。

所以本次整体为 `down-weighted`。它提供一条接收方响应正证据，也提供一条任务边界
负证据：**这个近对向场景不适合用当前有限时域的单区间 `c` 指标给出闭合冲突裁决。**

## 1. 实验是什么

背景使用 HUGSIM 已有的 `scene-0041` 重建，没有重新训练场景。自车固定为 released
metadata 的左转路径；同一个 RealCar actor 沿 world `z=30 m`、heading `+90°`
以 `4 m/s` 匀速行驶。三档只改变actor到达固定冲突中心 `(-12.5,30) m` 的时间：

| 条件 | 到达时刻 | 公共参考路径的预注册 `c` |
|---|---:|---:|
| separated | 2.827 s | +0.50 s |
| boundary | 3.327 s | 0.00 s |
| overlap | 4.327 s | -1.00 s |

其中 `c>0` 表示分时占用，`c=0` 表示刚好接触，`c<0` 表示占用重叠；数值误差界限
为 `±0.02 s`。该零点只是几何集合边界，不是现实安全阈值。

最初的 `2 m/s` dry run 暴露出短窗口两端截断，因此未作为正式条件。正式设计在看
SparseDrive输出之前改为 `4 m/s`，并用完整180帧、14.816秒元数据闭合三档占用。

## 2. 动态和输入资格

- 三档各有180个显式actor transform；最大时间步 `0.091606 s`；
- 水平速度误差为 `0 m/s`，最大逐步位置残差 `3.54e-15 m`；
- 没有 ConstantPlanner reset 预步，也没有尾窗状态填充；
- SparseDrive历史固定为 source frames `30,36,42,48`，command固定为
  `[0,1,0]`；
- frame 48三档至少在一个相机中有明确actor RGB支撑；
- 声明Gaussian投影对RGB差分覆盖率全部为 `1.000`，最大中心偏差 `2.55 px`。

投影通过只说明metadata transform、actor checkpoint、相机和HUGSIM自己的RGB栅格化
相互一致，不能证明三维位置或画面符合现实。

可视化：

- `artifacts/hugsim_scene0041_opposing_path_dynamic/formal-render-frame048-run001/pose_variants_render_only.png`
- `artifacts/hugsim_scene0041_opposing_path_dynamic/formal-projection-separated-frame048-run001/actor_projection_alignment.png`
- `artifacts/hugsim_scene0041_opposing_path_dynamic/formal-projection-boundary-frame048-run001/actor_projection_alignment.png`
- `artifacts/hugsim_scene0041_opposing_path_dynamic/formal-projection-overlap-frame048-run001/actor_projection_alignment.png`

## 3. SparseDrive观察到了什么

每档独立reset运行两次。最大重复差异为 `3.0518e-5 m`，而相邻条件的最大计划差异为：

| 比较 | 最大计划差异 |
|---|---:|
| separated vs boundary | 0.234 m |
| boundary vs overlap | 1.118 m |

因此“接收方产生了可分辨响应”是 `accepted`。三档均选择原生mode `2`，不是mode切换
造成的表面差异。

但3秒末端纵向进展为：

| 条件 | final forward |
|---|---:|
| separated | 11.364 m |
| boundary | 11.168 m |
| overlap | 12.286 m |

`overlap`反而比`boundary`多前进 `1.118 m`。因此“纵向进展随冲突增强而单调减少”
这个辅助主张为 `rejected`。这不能直接归因于SparseDrive错误或HUGSIM错误，因为纵向
进展本来就不是冲突缓解的完整指标。

## 4. 为什么主指标没有给出通过/失败

把三条计划放回同一个冲突区后：

- 三条计划在3秒末端仍占用冲突区，全部为 `censored_right`；
- separated和overlap还各出现两个短占用区间；
- 预注册要求单一、完整、未截断区间，因此三档计划 `c` 均必须为 `null`。

这不是程序崩溃，而是指标按规定fail closed。对应结论：

- “三档计划的有限 `c` 冲突缓解顺序可裁决”：`rejected`；
- “这个3秒接收方对该近对向狭长冲突区具有完整任务证据”：`down-weighted`；
- “HUGSIM普遍可信或SparseDrive现实安全”：`rejected`，超出证据范围。

响应俯视图：

`artifacts/hugsim_scene0041_opposing_path_dynamic/sparsedrive-response-run002/sparsedrive_opposing_path_response.png`

## 5. 研究意义

本次把三个问题分开了：

1. HUGSIM能否生成规定的反事实动态和RGB：本场景内通过；
2. 固定AD是否感受到变化：通过，并且远大于重复噪声；
3. 当前指标能否判断AD是否正确缓解冲突：不能，因为任务空间长度与AD输出时域不匹配。

因此下一步不应修改本次判据来追求“通过”，也不应继续在同一近对向场景上堆曲线。
应先找一个交叉角更大、冲突区更紧凑、能够在3秒计划内形成单一完整占用区间的几何
任务；几何资格通过后再预注册并运行AD。
