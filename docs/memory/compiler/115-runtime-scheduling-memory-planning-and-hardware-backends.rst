第115章：Runtime Scheduling, Memory Planning, and Hardware Backends
==================================================================

核心知识点
----------

* AI compiler 生成 kernel/executable 后，runtime 仍要完成输入绑定、guard 检查、executable 选择、buffer 分配、queue/stream 提交、同步和输出返回。
* Runtime 面对的是一次具体 invocation，因此它看到真实 shape、dtype、device、memory address 与当前设备状态；这些事实决定缓存命中、后端选择和是否需要 fallback。
* “选择 executable”与“提交 kernel”是不同阶段。前者处理 guard、cache、provider/backend 与 specialization，后者处理真实设备队列、launch、同步和执行。
* Memory planning 根据 tensor size、lifetime、memory space、alignment、alias 和 output ownership 安排物理 buffer；峰值内存由同一时刻仍活跃的 buffer 决定。
* Buffer reuse 的核心前提是生命周期不重叠且语义允许别名。某个中间值若还有后续 consumer，就不能被下一结果提前覆盖。
* Dynamic shape 会让 buffer size 与 memory plan 参数化。系统可以按真实 shape 动态分配，也可以按 profile 最大值预留，或为常见 shape bucket 维护多套计划。
* CPU、GPU、TPU、NPU 与自定义 accelerator 的 backend constraints 不同：它们在并行粒度、memory hierarchy、layout、supported ops、submission model 和 dynamic-shape support 上都可能不同。
* Backend partition/fallback 直接影响性能。一个 unsupported op 可能把图切成多个子图，并引入 host↔device 或 device↔device 数据往返。
* 高性能 kernel 不能抵消频繁隐式拷贝、同步、fallback 或重复编译；完整调用延迟必须把 runtime orchestration 一起计入。
* Compilation cache 通常由 graph/model identity、backend、shape/profile、dtype、layout、device capability 和 compiler options 等共同形成 key。
* Runtime guard 检查当前输入是否满足 cached executable 的 specialization 前提；guard miss 可以触发另一个 executable、重新编译、fallback 或报错。
* 完全静态 specialization 能提供更强 tiling、buffer sizing 与 library tactic 选择，但会增加编译版本；symbolic shape 减少版本数量，却需要更多运行时参数和边界处理。
* 不同 backend 的数值结果可能因 dtype、fusion、reduction order、quantization 和 library implementation 出现合理误差；诊断必须区分容差差异与真实语义错误。
* AI 编译性能必须跨 graph、kernel、runtime、memory 和 hardware backend 闭合分析，单独看 FLOPs 或单个 kernel 时间都不够。

关键路径
--------

一次推理调用：

::

   bind runtime inputs
   → validate shape/dtype/device guards
   → lookup/select executable
   → prepare persistent + temporary buffers
   → enqueue kernels / copies
   → synchronize required dependencies
   → return outputs
   → release or recycle temporaries

动态 shape 与 cache：

::

   runtime shape
   → evaluate guard/profile
   → cache hit: reuse specialized executable + memory plan
   → cache miss: select broader executable / compile new variant / fallback
   → update cache

Backend 排查：

::

   graph partition
   → supported subgraphs per backend
   → detect fallback boundaries
   → inspect device copies and synchronization
   → inspect kernel fusion/layout
   → inspect memory peak and cache behavior
   → measure end-to-end latency

概念辨析
--------

* **Compiler 与 runtime**：compiler 生成优化后的表示和 executable，runtime 把它们与一次真实输入、设备、内存和队列连接起来。
* **Kernel time 与 invocation latency**：前者只测设备计算，后者还包含拷贝、guard、cache、launch、同步和 fallback。
* **Memory allocation 与 memory planning**：allocation 是拿到物理空间，planning 是根据生命周期决定哪些逻辑 tensor 应共享哪些空间。
* **Dynamic shape 与 recompilation**：动态 shape 不必每次重编译；是否重编取决于 symbolic coverage、guard 和 cache 策略。
* **Backend support 与 backend performance**：某后端能执行一个 op，不代表它能高效执行整个图；partition、layout 与数据边界同样重要。

本章结论
--------

AI 编译系统的最终执行链是 ``Graph/Kernel Compilation → Runtime Guards/Cache → Memory Plan → Backend Submission → Hardware Execution``。性能来自图优化、kernel schedule、buffer 生命周期、cache 粒度、fallback 边界与硬件能力的共同设计；任何一层失配，都可能吞掉前面编译优化的收益。
