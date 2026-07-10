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

## 2. 当前最高优先级

当前第一阶段审计对象是：

**HUGSIM 这一类真实日志重建型闭环仿真器**

理由：

HUGSIM 是 3DGS-based、真实日志/真实数据集驱动、传感器级、闭环、代码公开的自动驾驶仿真工作。相比 OmniDreams / Cosmos，它更适合作为当前阶段的 runnable target，用来先打通 credibility audit workflow。

当前不再以 OmniDreams / Cosmos 为第一运行目标。OmniDreams 已被移入 `docs/future/`，作为未来生成式世界模型闭环仿真的对照对象。

当前主线是：

> 先用 HUGSIM 建立 closed-loop evidence pipeline，再基于真实运行证据发展可信验证方法和后续量化指标。

---

## 3. 当前阶段目的与项目总目标的区别

项目总目标是研究 **闭环仿真结果能否作为自动驾驶模型评估的可信证据**。

当前 HUGSIM 阶段的目的更具体：

> 搭建 HUGSIM closed-loop evidence pipeline smoke test，并验证我们能否从真实闭环仿真器中收集足够证据，用于后续可信性判定方法和指标设计。

因此，当前 HUGSIM 实验不是为了：

- 证明 HUGSIM 本身可信；
- 复现完整 HUGSIM benchmark；
- 评测 UniAD / VAD / LTF 的真实性能；
- 提出最终 simulator credibility score。

当前 accepted / down-weighted / rejected 是 **证据处理方式**，不是项目总目标，也不是最终量化指标。

---

## 4. 当前方法路线

当前采用四步路线：

### Step 1 — Source Availability Gate

先判断论文、代码、模型、数据、runtime、评估脚本是否公开可查。

### Step 2 — Closed-loop Evidence Completeness

判断一次闭环仿真是否产生完整证据链，包括：

- observation；
- planner / agent output；
- action；
- ego / actor state update；
- metrics；
- output files。

### Step 3 — Segment-level Evidence Judgment

对单个 closed-loop segment 做 evidence qualification：

- accepted；
- down-weighted；
- rejected。

### Step 4 — Future Credibility Metric

在积累多个 run 和多个 segment 后，再定义量化 simulator credibility metric。

当前还不急于提出最终数值指标。先保证证据链和判定规则成立。

---

## 5. 对照对象定位

以下工作作为对照对象和历史脉络：

- NeuroNCAP
- UniSim
- AdvSim
- OmniDreams
- Cosmos

它们用于回答：

- 早期日志驱动 / 反事实 / 传感器级闭环仿真如何自证可信；
- 它们使用了哪些自证指标；
- 这些指标实际证明了什么；
- 这些指标没有证明什么；
- HUGSIM 相比 NeRF / earlier log-driven simulators 是否推进了可信评估；
- OmniDreams / Cosmos 作为生成式世界模型方向，未来是否能继承或替代 HUGSIM 类审计流程。

---

## 6. 主线研究问题

### RQ1

HUGSIM 如何证明自己的仿真结果可信？

### RQ2

HUGSIM 的指标是在验证仿真器可信性，还是只是在验证自动驾驶模型表现？

### RQ3

HUGSIM 是否能发现低可信反事实样本、3DGS 重建 artifact、遮挡错误、深度错误、几何关系不一致、时序关系不一致？

### RQ4

NeuroNCAP / UniSim / AdvSim / OmniDreams 的自证指标，能否迁移到 HUGSIM 上？

### RQ5

是否仍然需要一个 credibility audit layer，用来判断闭环测试证据应被 accepted / down-weighted / rejected？

---

## 7. 当前理论判断

真实日志驱动反事实闭环仿真是必要方向，但它不是天然可信。

端到端自动驾驶 / sensor-input E2E agent 的趋势使评估问题从 motion-level planning 推进到 sensor-to-action closed-loop evaluation。

3DGS-based reconstruction simulator 比 NeRF-based simulator 更接近当前实时可运行路线，但实时渲染和视觉逼真度不等于可信闭环评估。

因此，本项目的关键判断是：

> sensor-level closed-loop evaluation 变得不可回避；  
> counterfactual simulation 使 credibility audit 变得不可回避；  
> 3DGS / NeRF / world model 都必须接受 source availability 与 relation-level consistency 审计。

---

## 8. 当前工作原则

当前阶段坚持最小化，不走太远。

不急于：

- 提出完整 verifier；
- 复现所有系统；
- 生成大而全综述；
- 一次性写完所有 simulator cards；
- 跑完整 HUGSIM benchmark；
- 重新训练所有 3DGS 场景；
- 继续推进 Cosmos / OmniDreams 大模型运行。

当前只做一件事：

> 用 HUGSIM 跑通最小闭环证据链，并基于真实输出验证 accepted / down-weighted / rejected 证据规则是否可用。

---

## 9. 当前已完成事项

已完成：

- HUGSIM Source Availability Gate；
- HUGSIM pipeline / closed-loop mechanism 第一轮抽取；
- HUGSIM smoke-test plan；
- HUGSIM accepted / down-weighted / rejected 证据规则；
- 本地预检脚本 `scripts/check_hugsim_smoke_prereqs.py`；
- deterministic plan-pipe writer `scripts/hugsim_plan_pipe_writer.py`；
- HUGSIM CUDA / pixi 环境问题排查与 runbook；
- 第一份 run report `docs/runs/hugsim_smoke_test_001.md`。

当前第一份 run report 的性质：

> 环境安装与诊断报告，不是 closed-loop evidence 成功报告。

当前环境层面的重要进展：HUGSIM pixi 环境已通过 CUDA 12.1 / PyTorch cu121 / `TORCH_CUDA_ARCH_LIST=8.9` 路线修复，`gsplat`、`tinycudann`、`pytorch3d`、`hugsim_env` 已成功 import。

仍未完成：

- 下载并确认一个最小 public released scene / scenario；
- 修改 HUGSIM base config 到 `/home/yawei/...` 本地路径；
- 进入 `env.reset`；
- 创建并通过 `obs_pipe` / `plan_pipe`；
- 用 deterministic plan-pipe writer 跑通一个闭环片段；
- 生成 `data.pkl`、`video.mp4`、`infos.pkl`、`eval.json`、`ground.ply`、`scene.ply`；
- 生成第一条真实 closed-loop audit log record；
- 基于真实输出判断 accepted / down-weighted / rejected。

---

## 10. 术语澄清

### deterministic plan-pipe writer

它不是 AD agent，也不是模型评测对象。

它只是一个 deterministic dummy planner，用来向 HUGSIM 的 `plan_pipe` 写入简单轨迹，从而推动 simulator loop 继续执行。

它的作用是验证：

```text
obs_pipe / plan_pipe
→ trajectory-to-control
→ env.step
→ state update
→ output files
```

它不能用于解释真实自动驾驶模型性能。

### accepted / down-weighted / rejected

这是当前阶段的 evidence qualification label。

它既可用于筛选场景输出，也可作为未来 credibility metric 的基础，但它本身还不是完整数值指标。

### simulator credibility metric

尚未定义成最终数值指标。

当前已有的是证据判定规则；未来需要在多个真实 run / segment 积累后，再从 source availability、evidence completeness、relation consistency、artifact risk、event attribution confidence 等维度形成量化指标。

---

## 11. 当前文件结构

核心文件：

- `README.md`
- `PROJECT_STATE.md`
- `SOURCE_AVAILABILITY_GATE.md`
- `docs/hugsim_audit.md`
- `docs/hugsim_smoke_test_plan.md`
- `docs/hugsim_credibility_decision_rules.md`
- `docs/hugsim_cuda_pixi_runbook.md`
- `docs/runs/hugsim_smoke_test_001.md`

辅助文件：

- `docs/runnable_target_selection.md`
- `docs/comparison_notes.md`
- `docs/literature_matrix.md`
- `docs/codex_workflow.md`
- `docs/future/omnidreams_audit.md`
- `scripts/check_hugsim_smoke_prereqs.py`
- `scripts/hugsim_plan_pipe_writer.py`

---

## 12. 需要重点审计的可信性缺口

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

## 13. 当前下一步最小行动

下一步只做：

> 从“环境安装成功”推进到“第一段 HUGSIM closed-loop evidence 产生”。

当前已知 `/home/yawei` 有约 300GB 可用空间，因此下一步数据与输出应优先放在：

```text
/home/yawei/hugsim_assets
/home/yawei/hugsim_outputs
/home/yawei/hugsim_sample_data
```

不要继续依赖已满的 `/data`。

最小执行路径：

1. 确认 GPU-visible shell 下 HUGSIM pixi env 仍能 import `gsplat`、`tinycudann`、`pytorch3d`、`hugsim_env`；
2. 下载 sample_data 或必要 public released scene assets 到 `/home/yawei/...`；
3. 确认是否存在 `cfg.yaml`、`scene.pth`、`ground_param.pkl`；
4. 创建本地 smoke-test base config，避免原作者 `/nas/users/hyzhou/...` 路径；
5. 启动 HUGSIM debug / closed-loop path；
6. 用 deterministic plan-pipe writer 提供 deterministic plan；
7. 收集 `data.pkl`、`video.mp4`、`infos.pkl`、`eval.json`、`ground.ply`、`scene.ply`；
8. 写第一条 closed-loop credibility audit record。

不要同时展开 OmniDreams / Cosmos。
