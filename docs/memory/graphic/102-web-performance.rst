第102章：Web 图形性能
====================

核心知识点
----------

Web 图形性能必须拆成多段预算
   一帧同时经过资源加载、JavaScript、DOM/CSS、Canvas 命令录制、WebGL/WebGPU 提交、GPU pass、浏览器合成与显示。FPS 只是结果，优化必须先确定成本落在哪一段。

60 Hz 的理论帧窗口约为 16.67 ms
   实际应用还要给浏览器输入、样式、布局、合成和系统调度留余量。高刷新率设备预算更紧。稳定交互应关注 frame time percentile，而不是只看平均 FPS。

CPU 主线程瓶颈与 GPU 瓶颈需要不同证据
   主线程长任务、React/DOM 更新、对象分配和上传准备会同时拖慢输入与 rAF；GPU bottleneck 则需要 GPU timestamp、分辨率/效果降级对照、shader/pass timing 来证明。

DOM/CSS 管线仍会影响 Canvas 应用
   Style、Layout、Paint、Composite 和 Canvas GPU 输出最终汇合到同一页面。模型渲染本身很快，但材质面板重排、透明 overlay 或大面积滤镜仍可能让最终帧超预算。

Long Animation Frame 与 Performance Timeline 是现场证据
   LoAF、long task、User Timing、Resource Timing 与自定义 marker 可把真实用户卡顿映射到 script、layout、loading 和 render submit。单次开发机录屏不足以代表上线设备分布。

加载优化要分“首帧可见”和“完整质量”
   首帧只保留基础模型、低清贴图、默认材质、最小 pipeline；高清贴图、环境资源、可选部件和复杂 shader 后续渐进加载。这样能缩短白屏和首次可交互时间。

网络完成不等于图形资源 Ready
   图形资源还要经历 decode、CPU conversion、GPU allocation/upload、mipmap、shader/pipeline preparation。性能监控应记录从请求开始到资源第一次被 draw 的完整时间线。

Shader/Pipeline 编译也属于加载路径
   WebGL 可利用并行 shader compile 等机制避免首次使用阻塞；WebGPU 应预创建或异步创建热路径 pipeline。运行时第一次进入某材质才编译，容易制造交互尖峰。

WebGL/WebGPU 提交层应减少 Draw、State/Binding 和对象创建
   先按 pass/pipeline/material 排序，再使用 batching、instancing、资源表复用。每帧创建 buffer、texture、bind group、pipeline 或执行同步查询会增加浏览器验证和 CPU 提交成本。

GPU 像素成本主要受分辨率、Overdraw、Shader 与带宽影响
   Bloom、SSAO、SSR、透明、阴影和高 DPR 都会放大 fragment 与 render-target 成本。降低内部渲染分辨率后显著提速，通常说明像素成本主导。

上传应有每帧预算
   大 buffer、高清 texture 和 mip 生成应分批、预上传或渐进替换。高频小数据使用 ring/连续切片；暂停上传后帧尖峰消失，说明瓶颈在 decode/allocation/upload 而非 shader。

内存要区分 JS Heap、CPU 解码面和 GPU 资源
   压缩图片文件很小，解码像素、mip 链和 GPU texture 可能占用数十倍空间。内存诊断不能只看网络文件大小或 ``performance.memory``。

GC 应从热路径对象分配控制
   每帧创建数组、闭包、矩阵和临时状态包会增加 GC 周期。复用 typed array、对象池和持久 frame state，减少高频遥测对象，能降低周期性帧尖峰。

GPU Resource 需要显式预算与释放
   Texture、buffer、render target、pipeline/cache 应按数量、尺寸、最后使用帧和质量档位统计。WebGL context lost、WebGPU device lost、创建失败都应进入错误遥测。

持续监控比一次 Profiling 更重要
   线上至少记录加载、frame P50/P95/P99、输入响应/LoAF、draw/triangle/upload、GPU pass、内存、缓存命中和 GPU context/device error，并按浏览器、GPU、分辨率和质量档位分组。

优化必须由对照实验闭环
   关后处理、降分辨率、暂停上传、固定 DOM、禁用某 shader、减少 draw 等实验要对应明确指标变化。只有“动作→指标→阶段”一致时，优化结论才可靠。

关键路径
--------

帧预算：

::

   input
   → JS / state update
   → DOM style / layout / paint
   → Canvas command encoding
   → WebGL/WebGPU submit
   → GPU passes
   → browser composite
   → present

首帧：

::

   critical network resources
   → decode / parse
   → minimal GPU upload
   → shader / pipeline ready
   → first draw
   → first interactive frame
   → progressive high-quality assets

性能定位：

::

   frame percentile regression
   → main-thread timeline
   → DOM/layout/paint
   → API submit / upload
   → GPU timestamps / pass timings
   → resolution/effect A-B test
   → memory / GC / resource pressure

持续监控：

::

   Resource Timing + User Timing
   → frame time P50/P95/P99
   → LoAF / input latency
   → draw / upload / GPU pass metrics
   → JS + GPU memory estimates
   → context/device lost + validation errors
   → segment by device/browser/quality

概念辨析
--------

* **FPS 与 Frame Time Percentile**：FPS 是聚合结果，P95/P99 frame time 更能暴露交互尖峰。
* **CPU Frame Time 与 GPU Frame Time**：前者覆盖 JS/编码/提交，后者覆盖真实 GPU pass；两者可能并行且主瓶颈不同。
* **Network Size 与 Runtime Memory**：压缩资源大小不能代表解码面、mip 和 GPU 驻留占用。
* **首帧优化 与 总加载完成**：首帧追求最小可交互集合，完整资源可在之后渐进到达。
* **GC Pressure 与 GPU Memory Pressure**：一个来自 JS/CPU 对象生命周期，一个来自 texture/buffer/render target 等 GPU 资源。
* **平均性能 与 真实用户稳定性**：平均值会掩盖长尾，真实监控应关注 percentile、错误率和设备分组。
* **优化相关性 与 因果证据**：看到帧率变高不够，需要对应阶段指标变化证明该修改真正减少了目标成本。

本章结论
--------

Web 图形性能应按“Load—Main Thread—DOM/CSS—Graphics Submit—GPU Pass—Composite—Memory/Telemetry”理解。首帧慢先压 critical path，交互卡顿先分 CPU 与 GPU，周期性尖峰查上传和 GC，长会话退化查资源预算。最终目标不是在一台机器上得到最高 FPS，而是建立一套能持续测量、分层定位、验证回归并自动选择质量档位的 Web 图形性能系统。