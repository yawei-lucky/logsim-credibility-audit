# Literature Matrix

> Scope: lightweight index. Do not write a broad survey here.

| Work | Type | Log-Driven? | Counterfactual? | Sensor-Level? | Closed-Loop? | Self-Evidence Metrics | Credibility Gap | Role in This Project |
|---|---|---|---|---|---|---|---|---|
| HUGSIM | 3DGS-based log-driven closed-loop simulator | Yes, via captured driving datasets / posed images | Yes, via scenario configuration and actor behavior generation claims | Yes, RGB plus semantic / flow / depth claims | Yes | HD-Score: NC, DAC, TTC, COM, route completion | Metrics mainly score AD performance; need audit for reconstruction, extrapolated-view, actor insertion, occlusion, and relation consistency | Phase 1 main runnable target |
| NeuroNCAP | NeRF / NeuRAD-based photorealistic closed-loop simulator | Yes, via real driving logs | Yes, via safety scenario construction | Yes, camera rendering | Yes | NCAP-style safety evaluation / scenario scores | Renderer and scenario-editing artifacts may affect closed-loop evidence | Backup runnable comparison |
| UniSim | Neural closed-loop sensor simulator | TODO_SOURCE | TODO_SOURCE | TODO_SOURCE | TODO_SOURCE | TODO_SOURCE | TODO_SOURCE | Historical comparison |
| AdvSim | Adversarial scenario simulation / sensor update work | TODO_SOURCE | TODO_SOURCE | TODO_SOURCE | TODO_SOURCE | TODO_SOURCE | TODO_SOURCE | Historical comparison |
| OmniDreams | Generative world-model simulator | TODO_SOURCE | TODO_SOURCE | TODO_SOURCE | TODO_SOURCE | TODO_SOURCE | Full runtime not confirmed public; paper-reported evidence only unless artifacts are released | Future work / generative world-model comparison |
| Cosmos | Foundation world-model platform | Not an AV simulator by itself | Proxy only | Generative media / action-conditioned model claims | Not equivalent to OmniDreams closed-loop AV system | TODO_SOURCE | Heavy runtime; useful only as future proxy/smoke-test substrate | Future proxy, not Phase 1 |
