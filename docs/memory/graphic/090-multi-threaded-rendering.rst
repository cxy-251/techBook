第090章：多线程渲染
==================

核心知识点
----------

多线程渲染的目标是缩短 CPU 准备时间并保持 GPU 连续供给
   一帧在提交 GPU 前还要完成场景更新、剔除、材质分组、上传准备、descriptor 分配、command recording 与最终 submit。并行的价值来自把这些 CPU 工作拆给多个 worker，同时保持资源和提交顺序可验证。

多线程收益来自可并行录制，风险来自所有权模糊
   Worker 应读取冻结的 frame/pass 输入并输出 command material；不要让多个线程直接修改全局 renderer state。Command allocator、command list、upload slice、transient descriptor 区间都应有明确唯一写入者。

D3D11 与 D3D12 的线程模型不同
   D3D11 常用多个 deferred context 录制，再由 immediate context 播放；D3D12 让多个线程独立录制 command list，并显式提交到 direct/compute/copy queue。D3D12 同时要求应用管理 allocator、barrier、descriptor 与 fence 生命周期。

Command Allocator 不能被多个正在录制的 List 共享
   每个 recording worker 应获得独占 allocator/list。Allocator ``Reset`` 必须等 GPU 完成使用其旧命令后才能进行；CPU job 完成只能证明录制结束，不能证明 allocator 已可复用。

Queue Submit 是多线程工作的收束边界
   Worker 完成后只得到可提交的 command list；真正的执行顺序由 submit 线程/逻辑根据 pass graph、resource dependency 与 queue dependency 决定。Queue signal 权限集中能降低 worker 相互等待造成的死锁风险。

Ownership 应覆盖 CPU 与 GPU 两个层级
   CPU ownership 说明哪个线程可以写 allocator、descriptor、upload memory；GPU ownership 说明哪个 queue/pass 正在读写 resource。两者通过 job completion、barrier、queue wait 与 fence 形成完整交接证据。

Barrier 与 Fence 不能互相替代
   Transition/UAV/aliasing barrier 描述资源访问和状态顺序；fence 表示 GPU queue 执行进度。跨 queue 的 copy→graphics 或 compute→graphics 依赖通常既需要正确资源状态，也需要 signal/wait 连接执行流。

Upload Ring Buffer 应按 Slice 管理唯一写入与延迟回收
   多 worker 可以从线程安全分配器申请不重叠 slice，各自写入；提交后 slice 与 fence value 绑定，GPU 完成后才能复用。随机常量错位与贴图闪烁常来自过早覆盖 in-flight upload memory。

Descriptor 动态区域也属于 GPU 可见生命周期
   Worker 可写自己的 transient descriptor range，但 range 在 command list 提交后必须保持稳定直到 fence 完成。Descriptor slot 被另一线程或下一帧提前覆盖，会表现成随机材质、错误 buffer 或 device fault。

Frame Graph 是资源 Ownership 的天然记录器
   Pass graph 已经知道每个 pass 的读写资源、队列与顺序。将 barrier、queue wait 与 transient resource lifetime 从 frame graph 派生，比给每个资源加细锁更容易推理。

粗锁和过度细锁都会破坏扩展性
   Renderer 全局大锁会把多线程退化为串行；每个资源一个锁则让死锁和顺序关系难以证明。更稳定的策略是 immutable frame input + thread-local recording + centralized submit + fence-based recycle。

CPU Wait 与 GPU Wait 要区分
   CPU 等 fence 会直接拉长 frame time；queue wait 约束 GPU 执行顺序。能通过 queue dependency 解决的问题，不应默认让 render thread 阻塞等待 GPU。

多线程问题通常表现为随机视觉错误或帧时间尖峰
   随机错误高概率来自 resource lifetime、descriptor overwrite、barrier 缺失、allocator/list 生命周期或跨 queue 依赖；尖峰高概率来自 worker 负载不均、submit 等 job、CPU fence wait、queue gap 或 present pacing。

性能诊断必须同时看 Worker Timeline 与 GPU Queue Timeline
   Worker timeline 回答 task 切分与长尾，queue timeline 回答 GPU bubble、copy/compute/graphics overlap 与 fence wait。只看总 render thread 时间无法判断并行到底卡在哪里。

Task 粒度要避免“过细调度”与“单 Pass 长尾”
   每 draw 一个 task 会制造调度开销；整帧一个 recording task 又无法利用多核。通常按 pass、view、draw chunk 或对象批次拆分，再通过 profiler 观察最长 worker 与同步等待。

Present Pacing 是整条提交链的最终症状
   前面任何 CPU 长尾、queue wait 或 GPU pass 超预算都会传导到 present。诊断 present 抖动时，应向前检查 graphics queue 是否持续饱和、submit 是否延迟、frame fence 是否阻塞资源复用。

关键路径
--------

多线程 Frame Build：

::

   frame begin
   → freeze frame plan
   → scene update / culling / upload prepare jobs
   → allocate per-worker allocator/list/resources
   → parallel pass recording
   → close command lists
   → gather recorded passes
   → resolve barriers / queue dependencies
   → submit copy / compute / graphics queues
   → signal frame fence
   → present

资源交接：

::

   worker owns CPU slice / descriptor range
   → record resource use
   → command list close
   → queue submit
   → barrier + optional queue signal/wait
   → GPU consumes resource
   → fence reaches retire value
   → allocator / slice / descriptor reclaimed

帧时间诊断：

::

   worker task durations
   → longest recording job
   → submit-thread wait
   → command queue gaps
   → cross-queue waits
   → GPU pass timings
   → CPU fence waits
   → frame resource recycle
   → present pacing

概念辨析
--------

* **CPU Job Done 与 GPU Work Done**：前者表示录制/准备完成，后者必须由 fence 证明。
* **Command List 与 Command Allocator**：list 保存记录的命令，allocator 提供命令存储；allocator 生命周期受 GPU 使用进度约束。
* **Barrier 与 Queue Wait**：barrier管理资源访问状态，queue wait 管跨队列执行依赖。
* **Thread Ownership 与 Queue Ownership**：一个约束 CPU 谁可写对象，一个约束 GPU 哪条执行流读写资源。
* **Upload Buffer 与 Default Resource**：upload 通常是 CPU 写入 staging/constant 路径，default resource 是 GPU 高效访问目标，生命周期与同步方式不同。
* **锁同步 与 Fence 同步**：锁约束 CPU 线程并发，fence 证明 GPU 进度，不能混为同一层。
* **多线程录制 与 GPU 并行**：CPU 能并行录制不代表 GPU 自动并行，最终仍受 queue、resource dependency 与硬件执行能力限制。

本章结论
--------

多线程渲染应按“Frame Plan—Thread Ownership—Command Recording—Resource Ownership—Queue Submit—Fence—Present”理解。随机画面错误先查 allocator/list、descriptor/upload 生命周期、barrier 与跨 queue wait；帧时间尖峰则从 worker 长尾、submit 等待、queue gap、CPU fence wait 和 present pacing 逐层定位。真正可扩展的 renderer 不是增加更多线程，而是让每个线程写什么、每个 queue 读什么、何时交接以及用什么证据证明完成都清晰可推理。