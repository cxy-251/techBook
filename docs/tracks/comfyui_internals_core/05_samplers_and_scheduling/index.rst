========================================================================
第 5 模块：采样器数值解法与调度方程 (05_samplers_and_scheduling)
========================================================================

.. toctree::
   :maxdepth: 2
   :caption: 模块章节目录

   01_samplers_and_kdiffusion_wrapper
   02_noise_schedules_and_sigmas
   03_cfg_and_guidance_computation
   04_ode_sde_solvers_internals

模块架构概述
============

本模块深入剖析扩散模型生成阶段的核心计算：采样器数值微分方程（ODE/SDE）求解与调度方程。

ComfyUI 将学术界前沿的扩散模型采样算法转化为工程级的高性能推理内核：

1. **KSampler 与数值封装**：解析 ``comfy/samplers.py`` 与 ``k_diffusion`` 包装层，统一离散步长迭代、模型前向预测与潜变量状态更新。
2. **噪声时间表与 Sigmas 序列**：剖析 Beta、Cosine、Simple、Karras、Exponential 等噪声调度方程的数学推导与离散化实现。
3. **无分类器引导（CFG）计算**：解析正负向提示词的批处理推理（Batch Inference）、CFG 缩放方程、Rescale CFG 与动态阈值截断（Dynamic Thresholding）。
4. **ODE/SDE 求解器内核**：深度推导 Euler, Heun, DPM-Solver++, UniPC, LCM 等一阶、二阶及高阶预估-校正数值求解器的每步更新张量流。
