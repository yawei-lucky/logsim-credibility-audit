# Codex Next Task — opposing-path dynamic-contract qualification 001

> 这是当前唯一里程碑。静态 placement 只通过到“可渲染走廊候选”；在动态 future、
> projection 和冲突区规则通过前，不预注册正式响应实验、不运行 SparseDrive。

## 已确认与已纠正

- `docs/runs/intersection_task_boundary_qualification_001.md` 已冻结有符号占用时间
  净距的几何零边界；
- `docs/runs/hugsim_scene0041_actor_placement_setup_001.md` 找到 world `z=30 m`
  的铺装/可渲染静态走廊候选；
- 候选点 `(-12.5,30) m` 距 source-model path 最近点 `0.279 m`；
- ego 局部 heading `-71.49°`，actor heading `+90°`，差 `161.49°`；
- 因而机制已从错误的“横穿交通”纠正为**左转末段对向/近似正碰路径冲突**；
- placement 未查看 SparseDrive，但也没有资格化动态 future 或 box–RGB 对齐。

## 当前目标

只补正式预注册真正需要的两个执行资格和一个指标定义：

1. **动态合同**：在 released metadata timestamps 上生成显式恒速 actor transforms，
   核验速度、方向、时间连续性、完整 future 和只有到达相位发生变化；
2. **projection 合同**：把 actor model/box 投影到六相机 RGB，保存 overlay、可见相机、
   投影区域与 actor-only RGB 差分的对齐记录；
3. **冲突区合同**：冻结 `C` polygon、ego/actor footprint 与 yaw 来源、轨迹插值、
   时间离散误差，以及以下特殊分支：
   - plan 空间避开 `C`；
   - 只在 3 s 时域后进入；
   - 多次进入/离开；
   - 占用区间被窗口截断。

## 最小执行顺序

1. 先写 CPU generator/analyzer 与最小测试；
2. 生成一个 geometry-only dynamic dry run，不运行 SparseDrive；
3. 只渲染少量早于极近距裁切的 source frames，检查 projection；frame `60` 的
   `conflict/after` 不作为 AD 有效输入；
4. 独立审核动态、projection 和 `C` 定义；
5. 三项均通过后，才由几何反推 separated / boundary / overlap 到达相位并冻结
   正式预注册；
6. 正式刺激渲染通过后，下一里程碑才运行 SparseDrive。

## 必须保持

- ego 使用 released metadata 参考路径/时间，不复用旧 9 s 直行 rollout；
- 正式评估处于 source command `1` 共同上下文，prehistory 单独记录；
- actor 资产、尺寸、world `z=30 m` 候选走廊、heading `+90°` 和速度固定，只允许
  到达相位变化；
- explicit metadata transform 与普通 env `ConstantPlanner` reset 合同不可混用；
- source native dynamics 原样保留，audit actor 不覆盖 native ID；
- 不使用 HUGSIM TTC/PDMS、raw forward endpoint 或 SparseDrive 输出反调刺激；
- `c=0` 是占用集合边界，不是现实安全阈值。

## 停止条件

若动态 transform 不连续、projection 与 RGB 明显错位、`C` 对小离散变化不稳定，
或 special branch 无法 fail closed，则停止并保留负面证据，不运行 SparseDrive。

后续即使通过，也只形成“对向路径序数刺激”的内部/任务接收方证据；不得声称现实
安全、车道/路权真实性、响应幅度真实性、matched real–sim、闭环安全或 HUGSIM
普遍可信。
