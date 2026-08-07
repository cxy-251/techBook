第026章：动态 Shader 生成与热更新
================================

核心知识点
----------

动态 Shader 生成解决的是“同一视觉目标需要多份可执行变体”
   变体来源包括材质功能、平台后端、render pass、资源布局、pipeline state 和调试模式。系统输出可以是源码、编译参数、中间表示、shader module、reflection metadata 或完整 pipeline object；动态生成不等于运行时拼字符串，而是一套可追踪的变体生产流程。

编译期条件与运行时参数必须严格分开
   会改变代码结构、资源声明、入口函数、线程组大小或 pipeline 兼容性的条件适合进入编译期；颜色、强度、粗糙度、贴图索引等普通材质数值应留在 uniform/constant/storage buffer。把实例级数值写进 variant key 会导致无意义重编译和缓存爆炸。

不同 pass 应裁剪不同功能集合
   Shadow pass 只保留位置、skinning、alpha clip 等必要能力；opaque lighting 才需要 PBR、normal map、clearcoat；debug pass 只保留调试输出。让所有功能无差别进入所有 pass 会同时扩大 shader 代码、资源绑定和 pipeline 组合数量。

Variant key 是 shader 与 pipeline 的身份合同
   Shader module key 至少覆盖 source dependency hash、backend、stage、entry point、compiler profile 和宏；pipeline key 还要加入 resource layout、vertex layout、render target/depth format、blend、raster、multisample 等状态。Key 缺字段会错误复用，字段过多会制造低价值变体。

缓存应按对象层级分开
   Shader module cache 回答“这份字节码是否已有”，pipeline cache 回答“这组 shader 加固定状态是否已有可执行对象”，reflection cache 回答“资源与接口声明是什么”。三类缓存失效条件不同，混成一层会让依赖、热更新和问题定位失去精度。

Source dependency 必须包含 include 图
   主 shader 可能依赖 lighting、BRDF、debug 等公共文件。公共 include 修改后，应通过反向依赖索引使所有相关 variant 失效；只 hash 主文件会继续命中旧 module，造成源码与画面不一致。

Reflection 是热更新的资源安全边界
   编译完成后应读取 texture、sampler、buffer、push constant、vertex attribute 和 fragment output 声明，并与材质布局和 descriptor/root/argument layout 校验。Binding 被删除、改号或类型变化时，应明确重建布局或拒绝切换，不能直接拿旧绑定表套新 shader。

热更新要先准备新对象，再替换旧对象
   文件变化 → 定位受影响 variant → 编译 → reflection 校验 → 创建/查找 pipeline → frame boundary 安全切换。编译或 pipeline 创建失败时保留 last-known-good pipeline，让画面继续可用并把错误反馈到编辑器。

旧 pipeline 的生命周期要覆盖 in-flight frame
   已录制或正在执行的 command buffer 仍可能引用旧对象，因此不能在热更新时立即销毁。替换和回收应与 frame fence、generation 或 deferred destruction 结合，保证正在使用的对象保持有效。

变体爆炸来自编译期维度的乘法
   六个独立二值 feature 理论上可产生 64 个组合，再乘 pass、平台、sample count 与 attachment format 后数量迅速扩大。控制顺序是减少编译期维度、按 pass 裁剪、将数值开关移到运行时、预热高频组合并统计真实 useCount。

关键路径
--------

Variant 请求：

::

   material feature + pass + backend + source dependencies
   → 生成 ShaderModuleKey
   → 查 module cache
   → miss 时编译
   → reflection
   → 生成 PipelineKey
   → 查 pipeline cache
   → miss 时创建 pipeline
   → 绑定资源
   → draw/dispatch

热更新路径：

::

   文件或材质图变化
   → 查反向依赖找到受影响 variant
   → 后台/编辑器编译新 module
   → reflection 校验 layout
   → 创建或命中新 pipeline
   → 保留旧 pipeline
   → 在 frame boundary 切换 handle
   → fence 完成后延迟销毁旧对象
   → 画面验证与错误日志

变体数量控制：

::

   列出所有 feature toggle
   → 标记是否真正改变代码或资源声明
   → 数值与实例参数移出编译期
   → 按 shadow/depth/opaque/debug pass 裁剪 feature
   → 合并等价组合
   → 预热高频 pipeline
   → 记录 cache hit、compile time、create time 与 useCount

概念辨析
--------

* **Shader module key 与 pipeline key**：前者描述代码编译结果；后者还包含 vertex layout、attachment、blend、raster、sample 等固定状态。
* **宏开关与 uniform 参数**：宏可删除代码并改变资源声明，适合结构性变化；uniform 只改变数据，适合频繁数值变化。
* **源码热更新与资源热更新**：源码变化可能导致重编译和 pipeline 刷新；纹理或常量变化通常只更新资源数据，不需要重新生成 shader。
* **Reflection 与材质元数据**：reflection 来自实际编译 shader 的接口；材质元数据来自引擎约定。两者必须互相校验，不能只信任其中一个。
* **Cache miss 与 cache invalidation**：miss 表示当前 key 从未缓存；invalidation 表示依赖变化使旧 key 或旧对象不再有效，原因和处理不同。
* **Hot reload 与原地修改**：热更新应创建新对象并安全切换，不应修改正在被 GPU 使用的 pipeline/module。
* **动态分支与变体**：统一运行时分支可减少变体数量；每像素动态分支可能增加执行发散。应在编译成本、分支成本与资源布局之间权衡。
* **预编译与按需编译**：预编译减少运行时 hitch 但增加启动和缓存规模；按需编译降低预热成本但必须有异步队列、fallback 与缓存策略。

本章结论
--------

动态 Shader 系统的核心不是生成代码，而是控制“哪些条件产生新二进制、哪些条件只更新数据、缓存如何识别、热更新如何安全替换”。稳定系统应把 module、pipeline、reflection 分层缓存，用完整依赖 hash 管理失效，以 last-known-good pipeline 保证画面连续，并通过变体 useCount、cache hit、compile/create 时间持续压缩低价值组合；只有这样，材质灵活性与运行时稳定性才能同时成立。