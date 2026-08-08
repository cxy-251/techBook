WebGPU Resource, Queue, Shader, and Security Execution Path
==========================================================

核心知识点
----------

* WebGPU 资源生命周期从 ``GPUDevice`` 开始。buffer、texture、sampler、bind group 等对象都应明确创建者、用途、更新频率、复用周期与释放时机。
* WGSL shader module 是浏览器可验证的 GPU 程序输入。浏览器在进入底层驱动前执行语法、类型、资源访问和安全检查。
* render/compute pipeline 把 shader、vertex/layout、format、blend/depth、bind group layout 等执行配置固定成可重复使用对象；频繁重建 pipeline 会增加 CPU 侧成本。
* bind group 把 shader 需要的资源按预定义 layout 连接到执行管线；资源绑定规则是 CPU 数据模型与 GPU 程序之间的核心契约。
* command encoder 负责记录工作，render/compute pass 组织具体命令，``finish()`` 生成 command buffer，``queue.submit()`` 才把命令交给 GPU 执行。
* queue submission 是异步边界。JavaScript 返回只表示命令已经提交；GPU 可能仍在处理旧帧，资源复用和 readback 必须考虑 in-flight 工作。
* 显式同步点很贵。频繁 map/readback、等待 queue 完成或 CPU 每帧依赖 GPU 结果，会破坏流水并造成停顿。
* WebGPU 通过 validation error、error scope、uncaptured error 和 ``device.lost`` 把部分故障显式暴露给应用；错误恢复必须纳入资源重建和降级路径。
* WebGPU 安全模型要求资源初始化、边界检查、WGSL 验证和浏览器进程隔离，目的是避免页面读取其他进程/GPU 残留数据或导致驱动不稳定。

关键路径
--------

资源与 pipeline：

``GPUDevice → create Buffer/Texture → create ShaderModule → create Pipeline → create BindGroup``

单次提交：

``Application Update → CommandEncoder → Render/Compute Pass → CommandBuffer → GPUQueue.submit → GPU Execute → Present / Result``

读回路径：

``GPU Work → copy to mappable/readback buffer → wait for completion → mapAsync → CPU reads data``

故障路径：

``validation error / device lost → stop unsafe reuse → record evidence → recreate device/resources or degrade feature``

概念辨析
--------

* **command encoding ≠ command execution**：encoder 只记录工作，GPU 在 submit 之后异步执行。
* **shader module 创建成功 ≠ pipeline 一定可用**：pipeline 仍要满足 layout、format、feature 和资源绑定约束。
* **GPUBuffer ≠ 普通 JS ArrayBuffer**：GPU 资源受 usage、映射状态和同步规则约束。
* **error scope ≠ try/catch 的同步替代**：许多 GPU 错误异步暴露，需要围绕提交边界收集。
* **device lost ≠ 单个 draw 失败**：整个 device 下的 GPU 资源和 pipeline 都可能需要重建。

本章结论
--------

WebGPU 的执行模型建立在“显式资源 + 显式 pipeline + 记录命令 + 异步提交”之上。应用必须把 GPU 资源生命周期、绑定契约、CPU/GPU 同步、错误范围和 device loss 当作一级架构对象，才能同时获得性能、可恢复性与浏览器安全边界。