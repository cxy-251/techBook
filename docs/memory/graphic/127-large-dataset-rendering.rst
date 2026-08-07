第127章：大规模数据集渲染
========================

核心知识点
----------

大数据渲染的核心是 Working Set 管理
   完整数据集可能远大于 CPU 内存和 GPU 显存，渲染器真正需要的是“当前视图可见、当前任务需要、当前预算允许”的数据块集合。

数据规模会同时压到 Storage、CPU、GPU 与 Interaction
   磁盘/网络负责请求和传输，CPU 负责索引、解压和整理，GPU 负责 resident resource 与绘制，交互层负责在数据未完全到达时维持稳定反馈。必须先分清瓶颈在哪一层。

Chunk/Tile/Brick 是独立调度单元
   二维瓦片、八叉树节点、体数据 brick、meshlet/cluster 都承担同一职责：可独立查询、加载、解压、上传、缓存、淘汰和渲染。

分块粒度要平衡调度与视觉误差
   块太大时首次进入区域的读取/上传延迟高；块太小时请求、metadata、绑定和调度开销高。合理粒度同时考虑压缩后字节数、屏幕覆盖、几何误差和交互频率。

LOD 应以 Screen-Space Error 为主线
   先剔除不可见块，再估计屏幕贡献和误差，随后检查资源预算并决定是否展开子层级。只按相机距离选 LOD 容易在长焦、斜视和高 DPI 场景失真。

LOD 选择还需要时间稳定性
   相机小幅移动时不应频繁在层级间翻转。Hysteresis、父节点保留、子节点渐进替换和短暂 cross-fade 可减少 pop、闪烁和密度突变。

Out-of-Core 是跨 IO、CPU、GPU 的生命周期系统
   常见状态包括 requested/pending、CPU staging、GPU resident、evicted、failed。每个块都需要 priority、version、last-used、byte size 和 fallback 状态。

数据缺失是运行时常态，不应视为异常分支
   缺失块可以先由父级 LOD、低分辨率 brick、低 mip 或占位结果替代。用户需要知道当前区域是 complete、partial、fallback 还是 failed。

缓存至少要区分 CPU 与 GPU 层
   CPU cache 保留解压或已解析数据，GPU cache 保留可直接绘制资源。二者容量、淘汰时机和访问成本不同，不能只用一个全局 LRU 粗暴管理。

淘汰策略应结合可见性和重载成本
   最近不可见、低优先级、低屏幕贡献且可快速重载的块最适合先淘汰。高成本远程数据或即将重新进入视野的数据应适当保留。

异步请求必须支持过期与取消
   用户快速移动相机时，旧区域请求可能已经失去价值。调度器应能降低优先级、取消或只写缓存，不能让旧结果覆盖当前视图状态。

压缩优化必须同时看 Ratio、Decode 与 Random Access
   压缩率高不等于总成本低。大数据渲染还关心解压耗时、是否支持块级随机访问、GPU upload 字节数和 shader 解码开销。

不同属性应采用不同压缩策略
   点云位置关心几何误差，颜色关心视觉差异，分类标签必须保持离散准确，时间戳和低频属性可按需加载。统一压缩格式往往浪费带宽或破坏语义。

Progressive Transmission 让画面从粗到细收敛
   先传父节点、低 mip、低分辨率 brick 或代表点，再补充高精度子块。交互中先获得空间稳定和语义正确，再逐步提高细节。

GPU 上传也需要 Budget
   每帧 upload bytes、copy queue 时间、resource creation 和 descriptor 更新都可能造成 spike。Streaming manager 应限制每帧上传量，避免数据到达反而拖垮当前 frame。

Debug Overlay 应显示数据生命周期
   Resident、pending、fallback、failed、LOD level、cache hit、missing tile 等状态用颜色或边框直接可视化，比单看 FPS 更容易定位空洞和闪烁来源。

可扩展性必须通过多维证据验证
   数据规模扩大时，应同时观察 IO throughput、request latency、CPU decode、GPU memory、cache hit、eviction、frame time、input latency 和 quality level。只证明“大文件能打开”不代表架构可扩展。

质量降级应有明确边界
   显存或网络不足时，可以降低点密度、使用父节点、增大体数据步长、降低 texture mip 或暂停远处细节；但坐标、主要结构和用户当前选区应尽量保持稳定。

关键路径
--------

大数据 Frame：

::

   camera / interaction
   → visibility query
   → screen-space LOD selection
   → cache lookup
   → resident blocks draw immediately
   → missing blocks async request
   → decode / transform
   → upload budget
   → publish resident version
   → progressive refinement

Out-of-Core 生命周期：

::

   block requested
   → pending IO
   → CPU staging/decode
   → GPU upload
   → resident
   → used by frame
   → low priority / memory pressure
   → evict GPU
   → retain or evict CPU cache

扩展性诊断：

::

   dataset grows
   → measure IO
   → measure decode workers
   → measure GPU residency/cache
   → measure frame/P95/P99
   → inspect fallback quality
   → identify first saturated resource
   → adjust block/LOD/cache/upload policy

概念辨析
--------

* **Chunk 与 LOD**：chunk 是调度单位，LOD 是不同精度层级；二者通常组合使用。
* **Out-of-Core 与 Streaming**：Out-of-Core 是超容量资源管理体系，streaming 是其中的数据搬运机制。
* **CPU Cache 与 GPU Residency**：CPU cache 便于快速重新上传，GPU residency 才能直接参与绘制。
* **Compression Ratio 与 End-to-End Cost**：压缩率只描述字节减少，不包含解压、随机访问和上传成本。
* **Missing Data 与 Low LOD**：缺数据表示结果尚未到达，低 LOD 表示已有可用但精度较低的替代数据。
* **Average FPS 与 Scalability**：平均帧率不能说明请求长尾、缓存抖动和交互延迟是否稳定。

本章结论
--------

大规模数据集渲染应按“Spatial Partition—LOD—Cache—Out-of-Core—Transfer/Decode—GPU Residency—Progressive Quality—Evidence”理解。系统不追求让完整数据常驻，而是持续维护最有价值的当前工作集。真正可扩展的架构会在数据规模继续增长时保持资源占用可控、交互持续响应，并让画质降级过程可解释、可恢复。