第109章：OpenCL 基础
===================

核心知识点
----------

OpenCL 是面向异构设备的开放通用计算模型
   Host 负责枚举 platform、选择 device、创建 context/queue、构建 program/kernel、管理 memory object 与 event；Device 执行 kernel。目标设备可以是 GPU、CPU、DSP、FPGA 等不同计算单元。

跨平台来自统一抽象，不代表硬件行为完全一致
   相同 API 可以组织不同设备上的计算，但 OpenCL version、image、SVM、subgroup、SPIR-V、外部内存和互操作能力都需要运行时 query。性能与兼容路径必须建立 device profile。

Platform、Device、Context、Queue 构成基础对象链
   Platform 表示某个 OpenCL 实现；device 是实际计算设备；context 是 program、memory、queue 的共同生命周期边界；command queue 是 host 向某个 device 提交命令的执行入口。

不要默认选择第一个 Platform/Device
   多 runtime 机器可能同时存在多个 CPU/GPU 实现。稳定程序应记录 vendor、version、extensions、device type、memory、work-group limit 等，再按任务和能力选设备。

In-Order Queue 适合正确性和基础调试
   ``write → kernel → read`` 在同一 in-order queue 中天然按顺序执行。Out-of-order queue 只有在 event dependency 明确且存在真实独立工作时才值得引入。

Event 同时承担依赖和 Profiling 证据
   Write、kernel、read 等 enqueue 命令都可产生 event。Event 可进入 wait list，也可记录 queued/submit/start/end 等时间，用来区分 host 提交、设备排队、kernel 和传输成本。

Program Build Log 是 Kernel 编译失败的第一证据
   Program 针对选定 device 构建。跨设备失败先查看 OpenCL C version、build options、extension 和完整 build log，而不是直接修改 kernel 算法。

Work-Item 与 Work-Group 决定 NDRange 执行粒度
   Global size 覆盖全部数据，local size 决定局部分组。线性图像/粒子任务常让一个 work-item 对应一个元素；local size 必须同时满足 device 与 kernel 的上限，并考虑 local memory、register 和 occupancy。

Memory Object 应按访问模式选择 Buffer 或 Image
   线性数组、粒子、prefix sum、compaction 适合 buffer；二维/三维采样、边界模式和硬件过滤更适合 image object。先用简单 buffer 路径建立正确性，再根据采样和互操作需求升级通常更稳。

数据传输经常比 Kernel 更贵
   一次轻量阈值 kernel 可能远快于 host→device write 和 device→host read。实时图形路径应优先共享同设备资源或让结果留在设备侧，避免每帧完整 round-trip。

Barrier 只同步 Work-Group 内的 Work-Item
   Kernel 内 barrier 不能提供所有 work-group 的全局同步。跨组 reduction、scan、compaction 通常需要多阶段 kernel + queue/event 依赖，而不是在一个 kernel 中等待所有工作组。

Local Size 是性能参数，不是越大越好
   较大 work-group 可能提高吞吐，也可能因 register/local memory 压力降低 occupancy。调优应结合 device limit、kernel work-group info、memory bandwidth 和 event timing。

图形互操作需要两条路径
   能共享 GPU resource 时，重点管理 acquire/release 与同步；无法互操作时，使用 staging/copy path，并把传输字节数和等待纳入预算。不能假设所有 OpenCL/图形 API/平台组合都支持零拷贝。

OpenCL 的适用场景更偏通用旁路计算
   图像处理、粒子/体数据、科学可视化、离线资产处理、跨设备工具链都适合。若任务紧贴现代 render graph 且目标平台已有成熟 compute shader，直接使用图形 API compute 往往对象链更短。

关键路径
--------

OpenCL 执行：

::

   enumerate platforms
   → select device by capability
   → create context
   → create profiling command queue
   → create/build program
   → inspect build log
   → create kernel
   → create buffer/image objects
   → set kernel arguments
   → enqueue write/acquire
   → enqueue NDRange kernel
   → enqueue read/release
   → event completion

故障定位：

::

   platform/device/version/extensions
   → context/object ownership
   → program build log
   → kernel args
   → global/local work size
   → memory transfer
   → event dependency
   → kernel timing / bandwidth

图形工作流：

::

   render/tool resource
   → shared interop or staging copy
   → OpenCL memory object
   → kernel processing
   → event / release
   → render pass or offline tool consumes output

概念辨析
--------

* **Platform 与 Device**：platform 是 OpenCL runtime 实现入口，device 是该 runtime 暴露的具体执行设备。
* **Context 与 Queue**：context 定义对象共享边界，queue 定义命令提交到某个 device 的执行流。
* **Work-Item 与 Work-Group**：前者是逻辑线程，后者是可共享 local memory 和 barrier 的局部分组。
* **In-Order 与 Out-of-Order Queue**：前者按提交顺序建立依赖，后者依赖显式 event 才能安全重排。
* **Buffer 与 Image Object**：buffer 偏线性结构化数据，image 偏采样、格式和二维/三维访问语义。
* **Event 与 Host Blocking**：event 可以表达异步依赖；host 阻塞等待会直接拉长 CPU frame latency。

本章结论
--------

OpenCL 应按“Platform—Device—Context—Queue—Program/Kernel—Memory—Event”理解。跨设备失败先查 capability 与 build log，结果错误再查参数、work size 和对象归属，性能差则先分离传输与 kernel 时间。OpenCL 的核心价值是以统一对象模型组织异构计算；真正稳定的图形应用必须同时管理设备能力、数据传输、队列依赖和互操作边界。