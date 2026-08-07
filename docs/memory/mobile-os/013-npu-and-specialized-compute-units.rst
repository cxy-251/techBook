第013章：NPU and Specialized Compute Units
==========================================

核心知识点
----------

* NPU、DSP、ISP、secure processor、sensor hub 等专用单元以更窄的任务范围换取更高吞吐或更低功耗；它们不是 CPU 的简单替代品。
* NPU 适合被 runtime/编译器支持的神经网络子图；DSP 适合音频、语音和连续信号处理；ISP 适合相机固定图像 pipeline；sensor hub 适合低功耗常驻感知；secure processor 适合密钥与可信运算。
* CPU、GPU、NPU 的核心差异可按灵活性、吞吐、延迟、内存访问、功耗和算子支持范围判断。CPU 最灵活，GPU 适合通用并行，NPU 在受支持模型上通常拥有更高能效。
* 模型“能运行”不等于“稳定跑在 NPU”。Runtime 会根据模型结构、算子支持、设备能力、内存布局和系统状态选择 CPU/GPU/NPU，并可能拆分子图或 fallback。
* 后端切换和子图拆分会产生 tensor copy、格式转换、cache 同步和 fence 等额外成本；端侧 AI 的瓶颈可能来自数据移动，而不是矩阵计算本身。
* Framework 提供 App 可见能力，runtime 负责模型编译、图划分和后端选择，system/vendor service 负责资源状态，driver 负责 queue、memory、priority 和硬件命令。
* 专用硬件通常通过共享 buffer 与 camera、graphics、audio 等 pipeline 协作。低复制路径要求双方接受兼容的数据格式和同步协议。
* 本地推理减少云端传输和网络延迟，也降低原始敏感数据外发范围；代价是模型占用、持续功耗、热预算和设备兼容性。
* 系统级智能功能应被理解为“数据源 → 专用处理单元 → runtime/service → App/系统结果”的能力链，而不是 App 直接控制某个 accelerator。

关键路径
--------

本地人像增强：

::

   camera sensor
   → ISP produces image buffer
   → ML runtime prepares tensor
   → choose NPU / GPU / CPU backend
   → driver submits accelerator work
   → inference result buffer
   → GPU / framework composes preview

后端选择：

::

   model graph
   → query supported operators / shapes
   → estimate latency and power
   → partition graph if needed
   → allocate compatible buffers
   → execute accelerator segments
   → fallback unsupported segments

专用能力进入 App：

::

   specialized hardware
   → kernel / vendor driver
   → runtime or system service
   → framework abstraction
   → app-visible model / media / sensor capability

概念辨析
--------

* **NPU 与 GPU**：两者都能处理并行计算，但 GPU 更通用，NPU 更依赖受支持的模型图和算子集合。
* **Hardware accelerator 与 public API**：App 通常调用 Core ML、ML runtime、media framework 等抽象，不应依赖某款设备的内部 accelerator 名称和队列细节。
* **推理耗时与端到端延迟**：单次 kernel 很快，tensor 准备、拷贝、排队和后处理仍可能使整条路径变慢。
* **本地推理与绝对隐私**：数据不上传能减少网络暴露，但本地处理仍受 App sandbox、模型权限、日志和存储保护等边界约束。
* **Fallback 与失败**：落到 CPU/GPU 不一定表示系统错误，它可能是模型兼容性和运行时策略的正常结果。

本章结论
--------

专用计算单元的价值在于把固定、高频、适合硬件化的工作从通用 CPU 路径中分离出来。分析端侧 AI 和系统智能能力时，应重点追踪模型图、runtime 后端选择、共享 buffer、driver queue、fallback、功耗和热状态，而不是只确认设备“有没有 NPU”。