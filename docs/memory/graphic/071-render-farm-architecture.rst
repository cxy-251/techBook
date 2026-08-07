第071章：Render Farm 架构
========================

核心知识点
----------

Render Farm 的目标是把离线渲染变成可调度、可恢复、可检查的生产系统
   单机渲染只关心命令是否执行，农场还必须管理 job、task、worker、资产、许可证、结果、重试和质量状态。最终交付事实来自“任务状态 + 输出文件 + QA 证据”，不能只看进程 exit code。

Dispatcher、Worker 与 Job Queue 必须职责分离
   Dispatcher 做全局资源匹配和调度决策；Worker 只拉取任务、准备环境、执行渲染、上传结果和上报心跳；Job Queue 持久化 priority、dependency、state、retry、owner、deadline 等生产状态。调度器重启后必须能从队列恢复事实。

Job Schema 应描述生产语义而不是只有命令字符串
   一个可复现任务至少要固定镜头、帧范围、资产快照、renderer version、render preset、AOV schema、资源需求、输出路径、重试策略和 QA 规则。命令只说明“运行什么”，schema 说明“这次运行代表哪个生产版本”。

任务切分首先考虑可恢复粒度
   Frame task 适合动画序列，失败可按帧重跑；Chunk 能减少启动和资产加载成本，但失败回滚范围更大；Tile 适合超高分辨率静帧，但必须处理 filter radius、denoise、deep data 和 AOV 接缝。切分策略不是纯调度问题，还会影响图像正确性。

Asset Cache 是吞吐系统，不只是文件缓存
   大量 Worker 同时从中心存储读取纹理、USD、Alembic、VDB 和 shader 包会形成网络瓶颈。稳定缓存需要以版本或 content hash 为键，并在任务开始前验证存在性、权限和一致性。缓存命中率、read bandwidth 和预热时间应进入农场指标。

License 应与 CPU、GPU、内存一样被建模为资源
   商业 renderer 或插件的 token 会限制真实并发。队列大量 ``waiting_license`` 时，继续扩 Worker 没有收益，只会制造更多等待。调度器应把许可证等待和计算资源不足分开统计。

Result Storage 是最终输出事实来源
   一帧“成功”至少应验证文件存在、尺寸合理、EXR header 正确、必要 AOV 完整、metadata 与 frame/job 对应。Result storage 还应保存日志、attempt id、checksum、QA 结果和归档索引，避免旧 Worker 的迟到上传覆盖新 attempt。

Worker Heartbeat 与 Lease 解决节点失联
   Dispatcher 为 task 分配租约，Worker 持续续约。心跳停止后任务回队列并产生新的 attempt。任何结果都必须绑定 attempt id，否则失联 Worker 恢复后可能上传旧结果，污染已经重跑成功的任务。

失败必须分类，而不是统一“重试”
   Missing asset、license denied、OOM、plugin missing、renderer crash、storage error、worker lost、user canceled 需要不同处理。临时节点错误可自动重试；资产缺失和配置错误应暂停同一 failure signature 的任务，避免重试风暴。

长尾要看 P95/P99 与阶段拆分
   平均帧时会掩盖少数超慢任务。应把总耗时拆成 setup、asset sync、license wait、render、upload、QA，再按 P50/P95/P99 比较。慢帧可能来自真实采样复杂度，也可能只是缓存 miss、内存换页或上传拥塞。

Autoscaling 必须基于瓶颈类型
   Queue depth 高且 Worker utilization 低，可能是资源标签过细；license wait 高时扩容无效；cache miss 与中心存储带宽已满时扩容会恶化 I/O；upload 饱和时新 Worker 只会把长尾转移到结果写入阶段。

最终渲染需要资产冻结与可回溯归档
   Final job 应绑定固定资产版本、renderer version、color config、AOV schema 和输出规则。归档不仅保存 EXR，还要保存 job schema、资产清单、失败修复记录、QA 结果与渲染 metadata，使未来能回答“这张图由哪些输入和哪次 attempt 产生”。

关键路径
--------

任务生命周期：

::

   shot / render package
   → job schema
   → job queue
   → dispatcher resource match
   → worker lease
   → asset / environment validation
   → license acquire
   → renderer execute
   → result upload
   → EXR / AOV QA
   → approved result
   → archive

失败恢复：

::

   heartbeat / task failure
   → classify failure signature
   → transient: retry with new attempt
   → resource mismatch: requeue to suitable worker
   → asset/config error: pause related tasks
   → fix manifest / environment
   → controlled rerun
   → validate result attempt

性能排查：

::

   queue depth / pending reason
   → worker utilization
   → license wait
   → cache hit / asset sync
   → render P50 / P95 / P99
   → peak memory
   → upload bandwidth
   → QA failure rate
   → decide scale / routing / asset / renderer action

概念辨析
--------

* **Job 与 Task**：Job 表示一次生产提交，Task 是可独立调度和重试的执行单元。
* **Dispatcher 与 Worker**：Dispatcher 决定“谁做什么”，Worker 只负责“把分配的任务执行完并上报事实”。
* **Queue State 与 Output Fact**：任务状态成功不等于图像可交付，输出文件和 QA 才是最终证据。
* **Frame、Chunk 与 Tile**：三者分别优化恢复粒度、启动复用和单帧并行，不能只按任务数量选择。
* **Asset Cache 与 Source Storage**：Cache 服务近端读取和吞吐，source storage 保存权威资产；cache 不能改变资产版本语义。
* **Retry 与 Repair**：临时执行失败适合 retry，稳定复现的资产/配置错误需要 repair 后再运行。
* **平均耗时与长尾**：平均值描述总体水平，P95/P99 决定最终交付是否被少数慢任务拖住。
* **Worker 扩容与吞吐提升**：只有计算节点不足时扩容才直接有效，license、存储和上传瓶颈需要分别处理。

本章结论
--------

Render Farm 应按“可复现提交—持久队列—资源匹配—受控执行—结果验证—失败恢复—归档复盘”理解。Dispatcher、Worker、Asset Cache、License Server 和 Result Storage 必须有明确边界；性能判断要把 setup、资产、授权、渲染、上传和 QA 拆开；可靠性则依赖 lease、attempt、failure signature 和资产冻结。农场规模来自节点数量，生产可靠性来自状态与证据的连续性。