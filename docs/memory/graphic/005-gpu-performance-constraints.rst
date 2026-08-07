第005章：GPU 性能约束
=====================

核心知识点
----------

性能结论必须落到帧预算
   60 FPS 的单帧预算约为 16.67 ms，120 FPS 约为 8.33 ms。测量时应区分 CPU frame time、GPU frame time 和包含 VSync、swapchain 与窗口合成的 wall-clock frame time；总帧时间不能直接说明瓶颈位于 shader。

帧耗时先分成 CPU、GPU 与 present
   CPU 路径包括场景遍历、命令录制、状态整理、descriptor 更新和 submit；GPU 路径包括 pass、draw/dispatch、shader、固定功能、内存和同步；present 路径包括图像获取、VSync、buffer count、队列背压和帧 pacing。分界完成后才进入局部优化。

GPU 约束可归为带宽、执行与资源竞争
   带宽约束来自 texture、buffer、render target、MSAA、resolve 和 copy 的字节流量；执行瓶颈来自 ALU、纹理单元、顶点处理、片元 overdraw、深度或混合等单元饱和；资源竞争来自 pass、queue、cache、buffer 与同步对象之间的串行和等待。

慢 pass 要通过变量实验归因
   耗时随分辨率或覆盖面积显著变化，优先检查片元和 render target 路径；随顶点或实例数变化，优先检查几何和实例数据；随采样数或格式位宽变化，优先检查纹理和带宽；随 draw 数变化，优先检查 CPU 提交与状态切换。一次只改变一个变量才能建立因果。

平均慢与偶发尖峰需要不同证据
   稳定超预算通常从最长 pass、draw、shader 和资源流量定位；偶发尖峰通常检查运行时 pipeline 创建、资源上传、内存分配、query readback、fence wait、swapchain 背压和热降频。平均值会掩盖尖峰，单帧 capture 也可能遗漏长期波动。

Draw call 优化存在边界
   batching、instancing、material sorting、multi-draw、indirect draw 与 bindless/descriptor table 可降低命令构建和绑定频率；代价可能是裁剪粒度变粗、实例数据读取增加、透明排序受限、资源表复杂和 GPU culling 同步。CPU 时间下降而 GPU 时间上升时，优化并未完成。

硬件特性改变成本分布
   tile-based renderer 更关注 attachment 的 load/store、tile locality、memoryless 资源和 pass 合并；immediate-mode renderer 更关注显存、ROP、overdraw 和全屏带宽；unified memory 更关注共享带宽与 CPU/GPU hazard；RT core 和 mesh shader 只加速特定阶段，仍受加速结构、材质、降噪、meshlet 与内存路径约束。

性能结论必须可复查
   有效结论应记录固定场景、目标帧、CPU/GPU/present 分界、慢 pass、资源和 shader 证据、单变量实验、性能收益、视觉影响与工程代价。工具名称不是证据，counter 与时间线必须对应同一帧、同一 pass 和同一渲染路径。

关键路径
--------

实时渲染性能分析路径：

::

   固定场景、相机、分辨率和质量配置
   → 记录 CPU、GPU、present 与 wall-clock 时间
   → 判断主要受限时间线
   → 把 GPU 帧拆成 pass
   → 在最慢 pass 中定位 draw 或 dispatch
   → 检查 shader、资源、overdraw、带宽和同步
   → 单独改变像素、几何、采样、格式或 draw 数量
   → 用同一测量边界验证根因与收益

减少 Draw call 的路径：

::

   按 pass 统计 draw 与 pipeline switch
   → opaque draw 按 pipeline 和 material 排序
   → 重复 mesh 改为 instancing
   → 稳定静态小网格按空间与材质 batching
   → 大量对象使用 indirect 或 multi-draw
   → 大量材质评估 descriptor table 或 bindless
   → 复测 CPU、GPU、裁剪、带宽与视觉正确性

硬件能力选择调优路径：

::

   查询 adapter、features、limits 与 format support
   → 识别 tile、immediate、unified memory 与专用单元特征
   → 建立 baseline 渲染路径
   → 为可用硬件选择 feature path
   → 对应检查 load/store、带宽、同步或专用阶段
   → 能力或预算不足时回退质量、格式、pass 或算法

概念辨析
--------

* **CPU bound 与 GPU bound**：CPU bound 表示 GPU 等待命令或应用逻辑；GPU bound 表示已提交工作执行超预算。两者可能在不同场景和帧阶段切换，必须通过时间线判断。
* **GPU time 与 present time**：GPU time 是渲染命令执行时间；present time 受 VSync、swapchain、合成和队列背压影响。GPU pass 已低于预算时，掉帧可能来自呈现链路。
* **带宽受限与计算受限**：带宽受限时成本随读写字节、分辨率、采样或格式变化；计算受限时成本更随指令量、循环、分支和执行单元利用率变化。
* **状态切换与 draw 数量**：draw 多通常伴随 pipeline、descriptor 和 buffer 变化，但二者不是同一指标；合并 draw 后若状态仍频繁变化或实例数据过重，收益可能有限。
* **batching 与 instancing**：batching 合并几何和提交，可能降低独立裁剪能力；instancing 复用 mesh，通过实例数据表达差异，更适合大量重复对象。
* **tile-based 与 immediate-mode**：前者尽量在 tile 内保留像素中间结果，跨 pass store/load 代价突出；后者更直接沿光栅化顺序访问外部显存和缓存。最佳 pass 组织不能跨架构照搬。
* **硬件加速与整体加速**：RT core、mesh shader 等只缩短特定阶段；若瓶颈转移到加速结构构建、材质访问、降噪、内存或提交，总帧时间未必下降。
* **优化收益与质量下降**：降低分辨率、格式或采样会减少工作量，也可能损害画面。性能调优结论必须同时记录视觉约束，不能把删减效果直接视为算法优化。

本章结论
--------

GPU 性能分析的核心是把一帧还原为 CPU 提交、GPU pass、资源流量、同步和呈现时间线，再通过单变量实验定位约束资源。排查时先建立预算和分界，随后抓住最长或波动最大的路径；选择 batching、instancing、格式压缩、pass 重组、异步队列或硬件特性前，必须验证成本会减少而不是转移，并同时保留正确性、画质和生命周期边界。