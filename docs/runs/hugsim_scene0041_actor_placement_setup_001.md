# HUGSIM scene-0041 actor placement setup 001

日期：2026-09-01

机器记录：`docs/runs/hugsim_scene0041_actor_placement_setup_001.json`

## 1. 目的和证据边界

本次只为后续前瞻交叉口冲突实验寻找一个可执行路径和冲突位置。它在运行前已声明
**排除在正式证据之外**，并且没有运行或查看 SparseDrive 输出。

setup 只检查：

- metadata 参考相机位姿下，actor world transform、ground height 和朝向是否可用；
- actor 是否在六相机 RGB 中出现在合理方向与尺度；
- 是否有明显漂浮、穿墙、背景撕裂或相机交接矛盾；
- 哪一小段内部 ground 支撑适合形成后续冲突区。

它不检查车道合法性、交通规则、actor 行为真实性、真实传感器一致性或 AD 响应。

## 2. 输入与工具资格

- scene archive SHA-256：
  `8d066a3594ad5dc0f43944cff7ec1a5aa364011792236551e4802c483d0550fe`；
- metadata：`/home/yawei/HUGSIM_assets/scenes/nuscenes/scene-0041/meta_data.json`；
- actor：`2024_07_05_15_57_10`，尺寸约
  `1.625 × 3.576 × 1.175 m`；
- actor checkpoint SHA-256：
  `3d8b314a9c2ae521464f3973edb4122958f8b580e4168bd6047fc0186094d006`；
- renderer 使用新增的 `--no-real-reference`：零图只满足 HUGSIM `Camera` 的非任务
  占位接口，报告中不生成 PSNR/SSIM/real-sim 指标；
- 所有 renderer manifest 均记录 `real_reference_available: false` 和
  `mean_metrics: null`。

render-only、placement provenance 和朝向关系的 14 项 CPU 单元测试连同既有
exact-pose / lead-metadata 测试均
通过。它保证“不读取真实 RGB、不误报真实对比指标”的软件合同，不保证渲染现实性。

## 3. 两阶段选点

### 3.1 宽范围扫描

在 world `z=30 m`、heading `+90°`（沿 world `+x`）固定同一车辆，扫描：

| 候选 | world `(x,z)` m | source frames | 结果 |
|---|---:|---|---|
| `left` | `(-8,30)` | `36,42,48` | 前视持续可见；接近参考转弯路径 |
| `center` | `(-2,30)` | `36,42,48` | 从前视过渡到右前视，较早越过参考路径 |
| `right` | `(4,30)` | `36,42,48` | 主要在右前视/右后视，位于路径远端 |

contact sheets：

- `artifacts/hugsim_scene0041_intersection_setup/render-frame036-run001/pose_variants_render_only.png`
- `artifacts/hugsim_scene0041_intersection_setup/render-frame042-run001/pose_variants_render_only.png`
- `artifacts/hugsim_scene0041_intersection_setup/render-frame048-run001/pose_variants_render_only.png`

候选未出现的相机与 factual render 的 PNG hash 完全相同；变化只出现在符合视向的
前视/右前视/右后视相机。这是一条渲染执行和相机方向证据，不是 sensor truth。

### 3.2 冲突位置细化

参考 ego model path 在相邻 metadata 帧的 world `(x,z)` 为：

| frame | timestamp s | ego model `(x,z)` m |
|---:|---:|---:|
| `60` | `5.0491` | `(-8.874, 28.575)` |
| `63` | `5.2747` | `(-10.413, 29.377)` |
| `66` | `5.5003` | `(-11.739, 29.773)` |
| `69` | `5.7505` | `(-13.547, 30.374)` |

因此 ego 路径在 frames `66–69` 之间穿过 `z≈30 m`、`x≈-12.5 m`。完整 provenance
重算得到：`(-12.5,30)` 最近 source-model pose 为 frame `68`、中心距
`0.279 m`；ego 局部切向 heading 为 `-71.49°`，actor heading 为 `+90°`，夹角
`161.49°`。所以这不是横穿交通，而是**左转末段对向/近似正碰路径**。

第二轮固定
`z=30 m` 和相同 heading，扫描 `x=-16,-12.5,-9 m`，并在 frames `54,60`
渲染：

- `before (-16,30)`：在前视中完整出现；
- `conflict (-12.5,30)`：随 ego 接近而按透视增大，在 frame 60 仍有完整可解释
  车体支撑；
- `after (-9,30)`：frame 60 已进入极近距/裁剪状态，适合作为 setup 极端检查，
  不选作固定冲突中心。

contact sheets：

- `artifacts/hugsim_scene0041_intersection_setup/render-frame054-run001/pose_variants_render_only.png`
- `artifacts/hugsim_scene0041_intersection_setup/render-frame060-run001/pose_variants_render_only.png`

五组 contact sheet 均未见明显漂浮、穿墙或无因复制；这是人工可见性审核，不能替代
独立三维真值。

frame `60` 的 `conflict/after` 已过近，`after` 出现严重多相机裁切；它只保留为
setup 极端几何检查，不进入后续 AD 有效输入窗口。

补充 provenance manifest：
`artifacts/hugsim_scene0041_intersection_setup/placement-metadata-run003/actor_placement_setup_manifest.json`。
它记录生成脚本、ground parameters、camera height、calibration `infos.pkl`、`l2c`
和 source-model 最近路径关系。run003 的 `before/conflict/after` metadata SHA-256
分别与用于现有 render 的 run002 完全相同，因此不重复渲染。

## 4. setup 冻结结果

当前只冻结以下**静态候选**，尚未通过动态正式实验 gate：

- actor corridor candidate：world `z=30.0 m` 的直线；
- actor forward：world `+x`，heading `+90°`；
- 近似冲突中心：world `(-12.5,30.0) m`；
- 机制标签：转弯末段对向路径冲突，不是横穿交通；
- 未来冲突区 `C` 候选：参考 ego footprint swept corridor 与 actor footprint
  swept corridor 的几何交集；其 polygon、footprint/yaw 来源、插值和误差尚待冻结；
- ego contract：metadata 参考 model path 和时间，不复用旧 9 s 直行 rollout；
- command：正式评估只保留 source command `1` 的共同上下文；prehistory 另行记录，
  不把 command 切换当 actor 效应；
- actor motion：当前仅做静态 transform；恒速连续 future 和相位合同尚未资格化。

选择依据仅为 source path、内部 ground、六相机 RGB/transform 和时域可用性；没有
读取 SparseDrive 规划结果，因此没有按 AD 结果挑选场景。

## 5. 裁决

| 主张 | 决定 | 依据 |
|---|---|---|
| render-only 模式不会伪造 real-sim 指标 | `accepted` | manifest 明确无 real reference，所有 real metric 为 null；CPU 合同测试通过 |
| `z=30 m, +x` 是可渲染铺装道路的静态走廊候选 | `accepted` | ground 支撑、五个 source pose contact sheet 和预期相机方向一致 |
| `(-12.5,30) m` 靠近 reference ego path | `accepted` | 最近 source-model pose 中心距 `0.279 m`；窄扫描具有完整可见支撑 |
| 该走廊代表横穿交通 | `rejected` | ego/actor heading 差约 `161.49°`，实际是对向近正碰关系 |
| 静态 setup 已资格化动态恒速 future、相位和连续性 | `rejected` | 还未生成或审计动态 metadata |
| transform/box 与 RGB 已有投影对齐证据 | `rejected` | 当前只有 transform、dimensions 和 RGB；尚无 box/point projection overlay |
| 该路径是精确合法车道或交通方向正确 | `rejected` | 本地无 HD map 或独立车道标注 |
| setup 是 HUGSIM 可信正证据 | `rejected` | 预先排除在正式证据之外，且位置由内部几何/渲染选择 |
| actor 渲染与真实传感器等效 | `rejected` | scene-0041 无 source RGB，未做 sensor reference 比较 |

静态候选 gate：`accepted`；直接进入正式动态实验的 gate：`rejected`。整体为
`down-weighted`。这不是实验失败，而是独立审核阻止了错误的“横穿车”机制标签和
过早的动态资格升级。

## 6. 下一步

在任何 SparseDrive 推理或正式预注册前：

1. 生成一个不看 SparseDrive 的恒速 dynamic metadata dry run，核验速度、时间和
   continuous future；
2. 生成 actor model/box 到六相机 RGB 的 projection overlay，记录对齐误差；
3. 冻结 swept-corridor `C` polygon、footprint/yaw、插值、离散误差及避开/截断/
   多次进出分支；
4. 再由几何反推 separated / boundary / overlap 三档；
5. 全部通过后才冻结正式预注册、完整渲染窗口并运行 SparseDrive。
