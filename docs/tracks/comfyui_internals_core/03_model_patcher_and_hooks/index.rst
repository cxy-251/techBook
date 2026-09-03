========================================================================
第 3 模块：动态权重修补与 LoRA/Hook 注入体系 (03_model_patcher_and_hooks)
========================================================================

.. toctree::
   :maxdepth: 2
   :caption: 模块章节目录

   01_model_patcher_core_architecture
   02_weight_patch_algebra_and_lora
   03_object_patches_and_forward_wrappers
   04_model_options_and_transformer_options

模块架构概述
============

本模块剖析 ComfyUI 最富扩展性与工程精巧度的核心组件——``ModelPatcher`` 与模型拦截 Hook 体系。

在生成式 AI 工作流中，基础大模型通常需要叠加多个 LoRA、ControlNet 注入、模型量化或自定义注意力算子。ComfyUI 避免了昂贵的基础模型硬拷贝，通过优雅的补丁代数与运行时劫持实现非破坏性组合：

1. **ModelPatcher 对象模型**：构建模型代理包装器，利用浅拷贝与克隆树追踪派生补丁链，确保多分支采样工作流零显存额外开销。
2. **权重差分注入代数**：实现低秩适配（LoRA/DoRA）在显存加载阶段的在线矩阵代数合并（``add_patches`` / ``calculate_weight``）与动态卸载还原。
3. **前向计算拦截与 Hook 链**：通过对象替换（``object_patches``）与 Forward 函数包装，实现跨层特征提取、注入与激活值引导。
4. **运行时上下文注入**：解剖 ``transformer_options`` 在 UNet 与 DiT 跨层前向传播过程中的参数广播与动态注意力控制。
