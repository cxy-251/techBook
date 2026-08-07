第084章：OpenGL Buffer 与 Texture
================================

核心知识点
----------

Buffer Object 本质是线性字节存储
   VBO、IBO、UBO、SSBO 等“身份”来自绑定 target、绑定方式和后续消费者。工程上应先判断数据是谁写、谁读、更新频率多高，再选择对象用途与更新策略。

VAO 记录顶点输入解释规则
   Vertex attribute 的 format、stride、offset、enable 与 buffer 关系由 VAO 保存。传统接口中 ``glVertexAttribPointer`` 会捕获当时的 ``GL_ARRAY_BUFFER``；DSA 接口可直接指定 VAO 与 vertex buffer，减少临时绑定状态。

IBO 绑定属于 VAO 状态
   ``GL_ELEMENT_ARRAY_BUFFER`` 与当前 VAO 关联。动态索引使用 ring buffer 时，draw 的 index offset、type 和当前写入 slice 必须一致，否则会出现随机三角形、UV 错接和几何破碎。

UBO 需要区分普通 Target Binding 与 Indexed Binding
   更新数据时可以绑定 ``GL_UNIFORM_BUFFER``；shader 真正读取的是 ``glBindBufferBase/Range`` 指向的 indexed binding point。Uniform block 与 binding point 的约定应固定在 shader/interface contract 中。

Texture Object 与 Sampler Object 应分离职责
   Texture 保存图像 storage、format、mip 和 swizzle；sampler 保存 wrap、min/mag filter、LOD clamp、compare mode。把采样状态从 texture 中抽离后，同一纹理可复用多套采样策略，资源管理也更清晰。

Texture Format 决定精度、色彩语义与带宽
   Albedo/UI 颜色需要考虑 sRGB internal format，normal/roughness/metallic 等数据贴图保持线性，HDR 中间纹理使用浮点格式，单通道 mask 应尽量使用 R 格式。格式过宽浪费带宽，过窄会引入 banding 或量化误差。

Mipmapping 同时影响画质与缓存局部性
   缺少 mip 的远处纹理容易 alias，并造成大 footprint 的随机采样。Atlas 生成 mip 时必须处理子图 padding，否则低 mip 会混入相邻图块产生串色。

动态 Buffer 的核心问题是 CPU 是否覆盖 GPU 仍在读取的区间
   每帧 ``glBufferSubData`` 重写同一存储可能触发隐式 stall。常见策略是 orphaning、invalidate、persistent mapped ring buffer，让 CPU 写入新的 slice，而不是等待旧 slice 释放。

Persistent Mapping 需要显式管理可见性与生命周期
   ``GL_MAP_PERSISTENT_BIT`` 让映射指针长期有效；非 coherent 路径需要 flush 写入区间；每个 slice 在 draw 后插入 fence，复用前检查 fence signal。指针持久并不意味着可以无同步覆盖同一内存。

Fence 应保护真正的 GPU 读取区间
   ``glFenceSync`` 应放在消费该 slice 的 draw 之后。后续复用该 slice 前检查 fence，证明 GPU 已越过读取命令。Fence 放在上传后、draw 前无法保护后续 draw。

Orphaning 与 Persistent Ring 解决同一类 Hazard
   Orphaning 通过放弃旧存储让 driver 提供新 backing；persistent ring 由应用显式划分多帧区间并同步。前者实现简单，后者更可控，选择依据是更新量、平台稳定性和 CPU stall 证据。

Interleaved 与 Planar Layout 由 Pass 的读取集合决定
   大多数 pass 读取全部顶点属性时 interleaved 更利于连续 fetch；depth-only 只读 position 时，planar 或独立 position buffer 能减少无效带宽。静态属性和动态 instance 数据也常拆开存储。

资源优化必须先定位瓶颈类别
   CPU map/update 阻塞先查同步与 slice 复用；GPU vertex input 高先查 stride 和无效属性；fragment 采样高先查 format、mip、filter、atlas locality；draw 提交高再看 texture/buffer state switching 与 batching。

关键路径
--------

动态几何上传：

::

   CPU generated vertices / indices
   → allocate ring slice
   → write mapped range
   → flush if non-coherent
   → VAO / IBO offset binding
   → draw consumes slice
   → glFenceSync after draw
   → mark slice in-flight
   → reuse only after fence signal

Texture 采样：

::

   source pixels
   → choose internal format
   → texture storage
   → upload base level
   → mip generation / padding
   → sampler object
   → texture unit + sampler unit
   → shader sampler binding
   → fragment sampling

性能排查：

::

   CPU update/map timing
   → overlap with in-flight range?
   → ring/orphan/fence strategy
   → vertex stride / attributes
   → texture format / mip / filter
   → cache locality / atlas padding
   → draw/resource switching
   → GPU bandwidth / overdraw

概念辨析
--------

* **Buffer Object 与 VBO/IBO/UBO**：底层都是字节存储，工程身份来自绑定与消费者。
* **Target Binding 与 Indexed Binding**：前者用于操作当前 buffer，后者把特定 buffer 区间连接到 shader binding point。
* **Texture 与 Sampler**：texture 描述图像内容，sampler 描述如何采样。
* **Internal Format 与 Upload Format**：internal format 决定 GPU 存储，上传 format/type 描述 CPU 输入布局。
* **Orphaning 与 Persistent Mapping**：一个依赖 driver 换存储，一个由应用显式管理 ring 与同步。
* **Flush 与 Invalidate**：flush 让新写入可见，invalidate 声明旧内容不再需要。
* **Interleaved 与 Planar**：前者优化共同读取，后者适合不同 pass 只读取部分属性。
* **CPU Stall 与 GPU Bandwidth**：前者通常是同步/更新路径问题，后者才是布局、格式和采样吞吐问题。

本章结论
--------

OpenGL buffer/texture 应按“数据生命周期—绑定语义—更新区间—同步—GPU 读取”理解。动态资源掉帧先查 CPU 是否覆盖仍在飞行的区间，再选择 orphaning 或 persistent ring；纹理串色先查 mip、padding、wrap 与 sampler；GPU 带宽高再看 vertex stride、属性集合和 texture format。高效资源路径的关键不是某个 API 名称，而是让每块数据的写者、读者、时间区间和格式都可推导、可同步、可测量。