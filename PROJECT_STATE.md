# Research Commander — LogSim Credibility Audit 状态总结

## 1. 项目定位

本项目研究 **日志驱动型反事实闭环仿真可信验证**。

研究对象不是普通 open-loop planning benchmark，也不是 motion-only simulation 或纯 CARLA 合成仿真，而是：

真实驾驶日志  
→ 可反事实修改  
→ 传感器级观测生成  
→ sensor-input E2E agent / 自动驾驶模型  
→ 输出轨迹或控制  
→ 闭环状态更新  
→ 连续 rollout  
→ 评估自动驾驶系统表现

核心问题不是“仿真器能不能生成好看的图像”，而是：

> 这些仿真器生成的闭环测试结果是否可信，是否足以支撑端到端自动驾驶模型的评估结论？

---

## 2. 当前阶段定位

当前第一阶段审计对象是：

**HUGSIM 这一类真实日志重建型闭环仿真器**

HUGSIM 是当前实验载体，不是本项目的最终目标。

当前阶段目标是用 HUGSIM 搭建并验证一条最小闭环证据链，用来发展后续的闭环仿真可信验证方法和指标。

当前 HUGSIM 实验的定位是：

> HUGSIM closed-loop evidence pipeline smoke test

也就是说，当前实验不是为了证明 HUGSIM 本身可信，也不是为了复现完整 benchmark，而是为了验证我们能否从一个真实闭环仿真器中稳定收集以下证据：

```text
scenario / scene source
→ sensor-level observation
→ planner output
→ control action
→ ego / actor state update
→ closed-loop rollout
→ metric event
→ credibility judgment basis
```

OmniDreams / Cosmos 暂时后移，作为未来生成式世界模型闭环仿真的对照与扩展方向。

---

## 3. 当前方法路线

当前采用四步路线：

### Step 1 — Source Availability Gate

先判断论文、代码、模型、数据、runtime、评估脚本是否公开可查。

### Step 2 — Closed-loop Evidence Completeness

判断一次闭环仿真是否产生了完整证据链，包括 observation、planner output、action、ego / actor state update、metrics 和输出文件。

### Step 3 — Segment-level Evidence Judgment

对单个 closed-loop segment 做 evidence qualification：

- accepted；
- down-weighted；
- rejected。

这里的 accepted / down-weighted / rejected 是当前阶段的证据处理方式，可用于场景筛选和证据质量管理；它不是项目总目标，也不是最终数值指标。

### Step 4 — Future Credibility Metric

在积累多个 run 和多个 segment 后，再定义量化的 simulator credibility metric。

当前不急于提出最终数值指标。先保证证据链和判定规则成立。

---

## 4. 主线研究问题

### RQ1

HUGSIM 如何证明自己的仿真结果可信？

### RQ2

HUGSIM 的指标是在验证仿真器可信性，还是只是在验证自动驾驶模型表现？

### RQ3

HUGSIM 是否能发现低可信反事实样本、3DGS 重建 artifact、遮挡错误、深度错误、几何关系不一致、时序关系不一致？

### RQ4

NeuroNCAP / UniSim / AdvSim / OmniDreams 的自证指标，能否迁移到 HUGSIM 上？

### RQ5

是否仍然需要一个 credibility audit layer，用来判断闭环测试证据应被 accepted、down-weighted、rejected？

---

## 5. 当前理论判断

真实日志驱动反事实闭环仿真是必要方向，但它不是天然可信。

端到端自动驾驶 / sensor-input E2E agent 的趋势使评估问题从 motion-level planning 推进到 sensor-to-action closed-loop evaluation。

3DGS-based reconstruction simulator 比 NeRF-based simulator 更接近当前实时可运行路线，但实时渲染和视觉逼真度不等于可信闭环评估。

因此，本项目的关键判断是：

> sensor-level closed-loop evaluation 变得不可回避；  
> counterfactual simulation 使 credibility audit 变得不可回避；  
> 3DGS / NeRF / world model 都必须接受 source availability 与 relation-level consistency 审计。

---

## 6. 当前已完成事项

已完成：

- HUGSIM Source Availability Gate；
- HUGSIM pipeline / closed-loop mechanism 第一轮抽取；
- HUGSIM smoke-test plan；
- HUGSIM accepted / down-weighted / rejected 证据规则；
- 本地预检脚本 `scripts/check_hugsim_smoke_prereqs.py`；
- deterministic plan-pipe writer `scripts/hugsim_plan_pipe_writer.py`；
- 第一份 HUGSIM run report；
- 第一份 run report 的 Research Commander review；
- HUGSIM CUDA / pixi 环境问题定位与 runbook；
- HUGSIM 已 clone 到 `/home/yawei/HUGSIM`；
- Pixi 环境已使用 PyTorch 2.4.1+cu121 / CUDA 12.1 安装成功；
- 在 GPU 可见的非沙箱环境中验证了 CUDA tensor，以及 `gsplat`、`tinycudann`、`pytorch3d`、`hugsim_env` 导入；
- 已确认首选最小场景 `scene-0383.zip` 可单独下载，约 628 MB；
- 已确认 `scene-0383-easy-00.yaml` 的 `plan_list` 为空，第一轮无需下载完整 3DRealCar 车辆库；
- 已下载并校验 `scene-0383.zip`，SHA-256 为 `cbd99a927316f7f795904c59350b7fced4b8f32a14506891720962e3e30e7f15`；
- 已创建本地 smoke-test base config 与 bounded debug runner；
- 已跑通 3 个 deterministic closed-loop steps，覆盖 observation FIFO、plan FIFO、trajectory-to-control、ego update、连续渲染和评分；
- 已生成 `data.pkl`、`video.mp4`、`infos.pkl`、`eval.json`、`ground.ply`、`scene.ply`、完整 observation pickle 与 audit summary；
- 已生成第一条真实 audit record，判定为 `down-weighted`。

第一份 run report 的结论是：

```text
not enough closed-loop evidence
```

原因是它只完成了环境层面的排障，没有生成 closed-loop segment。

第二份 run report 已完成：

```text
env.reset
→ obs_pipe
→ plan_pipe
→ env.step
→ output files
→ segment-level credibility judgment: down-weighted
```

---

## 7. 当前遗留问题

当前仍未完成：

- 对 RGB / semantic / depth 做像素级跨模态一致性检查；
- 运行更长的正常片段，验证状态、路线和渲染稳定性；
- 下载最小必要车辆资产并运行带动态 actor 的公开场景；
- 验证 collision / near-miss 等风险事件是否能区分 agent failure 与 simulator artifact；
- 将第一条 `down-weighted` 记录扩展成可复用的自动化 audit pipeline。

---

## 8. 当前文件结构

核心文件：

- `README.md`
- `PROJECT_STATE.md`
- `SOURCE_AVAILABILITY_GATE.md`
- `docs/hugsim_audit.md`
- `docs/hugsim_smoke_test_plan.md`
- `docs/hugsim_credibility_decision_rules.md`
- `docs/hugsim_cuda_pixi_runbook.md`
- `docs/runs/hugsim_smoke_test_001.md`
- `docs/runs/hugsim_smoke_test_001_review.md`
- `docs/runs/hugsim_smoke_test_002.md`
- `docs/runs/hugsim_smoke_test_002_audit.json`
- `CODEX_NEXT_TASK.md`

辅助文件：

- `docs/runnable_target_selection.md`
- `docs/comparison_notes.md`
- `docs/literature_matrix.md`
- `docs/codex_workflow.md`
- `docs/future/omnidreams_audit.md`
- `scripts/check_hugsim_smoke_prereqs.py`
- `scripts/hugsim_plan_pipe_writer.py`
- `scripts/run_hugsim_debug_smoke.py`
- `configs/hugsim/nuscenes_smoke_base.yaml`

---

## 9. 需要重点审计的可信性缺口

重点不是 photorealism，而是 task-relevant relational consistency。

需要关注：

- front / rear / left / right 是否稳定；
- same-lane / adjacent-lane / off-road 是否正确；
- approaching / receding 是否可信；
- occluding / occluded-by 是否一致；
- actor scale / orientation 是否稳定；
- extrapolated views 是否出现 lane / drivable area artifact；
- risk-increasing / risk-decreasing 是否由传感器、几何、地图、时序证据支持；
- collision / near-miss 是模型真实失败，还是仿真 artifact；
- 高风险关系是否有足够证据支撑。

---

## 10. 长期工作流

不依赖单个超长聊天窗口。

推荐结构：

ChatGPT Project / Custom GPT  
+ `PROJECT_STATE.md`  
+ GitHub / Codex 仓库  
+ 文献矩阵  
+ 最小文档集合

聊天窗口负责研究判断，长期记忆落到项目文件中。

每轮讨论结束，应更新：

- 当前研究判断；
- 主线问题；
- 支线问题；
- 暂缓问题；
- 下一步最小行动。

---

## 11. 当前下一步最小行动

下一步只做：

> 在已经跑通的 `scene-0383` deterministic loop 上补齐跨模态证据，并延长正常片段。

当前关键不是扩大文献范围，也不是定义最终数值指标，而是补齐：

1. 从现有 `observations.pkl` 导出 RGB / semantic / depth 对照图；
2. 检查道路边界、深度边缘、语义边缘和遮挡关系是否一致；
3. 将 bounded smoke test 从 3 steps 扩展到一个更长但仍可人工检查的片段；
4. 比较状态连续性、route completion、各相机渲染稳定性和评分变化；
5. 根据新增证据更新 `down-weighted` 判定，或在满足规则时升级为 `accepted`。

不要同时展开 OmniDreams / Cosmos。
