第155章：高性能 Packet Pipeline 的观测与优化
=============================================

本章必须记住
------------

#. 高性能 Packet Pipeline 的优化目标不是让某个局部 Counter 最大，而是让端到端 Packet Rate、CPU、P99、Drop 和正确性同时满足目标。
#. 观测前必须固定路径坐标：NIC Queue → Driver/NAPI → XDP Program → Redirect Target → AF_XDP Ring → User Worker → TX/下游。
#. 每一层都要有独立的输入、输出、Drop 和在途计数，才能定位 Packet 最后一次出现的位置。
#. 只比较 NIC 收包数和用户态收包数，无法区分 Driver、XDP、Redirect、Ring 和应用层丢失。
#. 包率、字节率和平均 Packet Size 必须同时记录；相同 Gbit/s 下 Packet/s 差异会显著改变 CPU 压力。
#. 策略性 ``XDP_DROP`` 与资源不足 Drop 必须分开计数，前者可能是正确业务结果，后者通常是容量或 Bug。
#. XDP Action Counter 至少应区分 PASS、DROP、TX、REDIRECT、ABORTED 和 Redirect Error。
#. Counter 应优先使用 Per-CPU Map 或驱动统计，避免每 Packet 竞争同一共享 Cache Line。
#. 用户态读取 Per-CPU Counter 时必须聚合所有 Possible/Online CPU，并处理 CPU Hotplug 与版本格式。
#. Counter 溢出、重置、Program Replace 和 Map Generation 会影响差值，监控系统必须记录对象版本。
#. ``ip -s link`` 提供 Netdev 汇总视图，不能包含所有硬件、XDP、Softnet、协议或 Socket Drop。
#. ``ethtool -S`` 提供驱动和 Queue 私有统计，字段名称、单位和重置语义由驱动定义。
#. `/proc/interrupts` 用于观察 IRQ Vector 的 CPU 分布，不表示后续 NAPI、RPS 或用户线程仍在同一 CPU。
#. `/proc/softirqs` 与 `/proc/net/softnet_stat` 提供软件接收压力证据，字段含义和格式具有版本边界。
#. ``bpftool prog show``、``map show``、``link show`` 用于确认 BPF 对象、类型、Attach、JIT 和关联 Map。
#. ``bpftool map dump`` 是状态快照，高频大 Map 全量 Dump 会产生明显控制面成本。
#. ``perf top/record`` 用于定位 Driver Poll、BPF JIT、Map Helper、内核网络路径和用户 Worker 的 CPU 时间。
#. CPU Profile 只能说明 CPU 在何处花时间，不能单独证明 Packet 在哪个 Queue 被丢弃。
#. Ftrace、Tracepoint 和 eBPF Trace 可连接 NAPI、XDP Redirect、Drop、XSK Wakeup 等事件，精确事件名随版本变化。
#. 逐 Packet Trace 会改变热路径，生产观测应优先使用 Counter、Sampling 和短时窗口。
#. 稳定关联应使用设备、Queue ID、CPU、Program/Map Generation、五元组或业务 Key，而不是只看时间相近。
#. XDP Program 加载失败与运行期性能问题属于两个阶段。
#. Verifier Rejection 应读取完整 Verifier Log，从第一处无法证明的 Pointer、Stack、Loop 或 Helper 参数开始修正。
#. Program 加载成功但 Counter 不增长，常见原因是 Attach 点、设备、Namespace、Mode 或流量路径错误。
#. Program Counter 增长而 CPU 过高，需要继续拆分指令、Map Lookup、Helper、Branch 和下游路径。
#. BPF Program 运行成本按事件频率放大，增加几十条指令在 Mpps 场景也可能成为显著 CPU。
#. 复杂 Header Parser 必须先确认真实流量需要哪些协议，不应为极少见封装让所有 Packet 经过深解析。
#. 将公共快速判断放在前部，让大多数 Packet 尽早 PASS/DROP，可减少平均指令和 Map 访问。
#. Branch 顺序应按真实流量分布优化，同时保持边界检查和可维护性。
#. Map Lookup 数量、Map Type 和 Key 大小都会影响热路径成本。
#. 共享 Hash Map 热点可能来自锁、Bucket 竞争、Allocator 或 Value Cache Line，而不是 BPF 指令本身。
#. Per-CPU Map 降低写竞争，控制面聚合和跨 CPU 一致性更复杂。
#. LRU Map 达到容量后会触发淘汰工作，表现可能是 CPU 上升和策略 Entry 抖动，而非直接 Update 失败。
#. Map Pressure 必须观察当前 Entry、最大容量、Update Error、Eviction 和业务命中率。
#. Map 容量扩大增加内存和 Cache Footprint，不自动提高性能。
#. Ring Buffer 或 Perf Event 输出满时，事件可以丢失或 Reserve 失败；没有事件不等于数据面没有执行。
#. AF_XDP 观测必须维护 FILL Produced、RX Consumed、TX Submitted、COMPLETION Reaped 和 User Free Frame 数。
#. Frame 总数守恒是发现 Leak、Double-submit 和未消费 Completion 的最直接检查。
#. FILL Ring 长期为空说明用户态归还 Frame 太慢或 Frame Pool 太小。
#. RX Ring 长期接近满说明用户 Worker 消费慢、未批量处理或调度不及时。
#. TX Ring 满说明内核/驱动消费跟不上；COMPLETION 积压说明用户态没有及时回收已完成 Frame。
#. XSKMAP Redirect 成功 Counter 增长但 RX Ring 不增长时，应检查 FILL、Queue Bind、Map Entry、Mode 和 Redirect Error。
#. 用户态 RX 增长但业务输出不增长时，瓶颈已离开内核收包路径，应 Profile 用户逻辑和下游系统。
#. Ring Size 增大可以吸收 Burst，也会增加驻留内存、排队时间和最坏延迟。
#. Batch Size 增大可以摊薄 Ring 同步和系统调用，也会增加首个 Packet 等待和一次性 CPU 占用。
#. Busy Poll 降低唤醒延迟，代价是专用 CPU、功耗和对同核任务的干扰。
#. Need-wakeup 可减少无效 Kick，但错误处理 Flag 会导致 TX/RX 停顿或额外系统调用。
#. Interrupt Coalescing、NAPI Budget、AF_XDP Batch 和 Busy Poll 位于不同层级，不能同时盲目增大。
#. 优化一个层级时要观察其是否把 Backlog 推到下一层，而不是只看当前层 Drop 下降。
#. RSS 把 Flow 分到 NIC RX Queue；IRQ Affinity 决定 Vector 首次在哪个 CPU 处理。
#. RPS 可以在软件层把 Packet 交给其它 CPU，可能破坏 XDP/AF_XDP Queue Locality。
#. XPS 影响发送 CPU/Flow 到 TX Queue 的映射，不改变 RX Queue。
#. AF_XDP 常以 Queue 为隔离单位，最佳起点通常是 Queue、IRQ、Worker 和 UMEM NUMA 对齐。
#. 单个热 Flow 不能被普通 RSS 无损拆到多个 Queue；增加 Queue 数不会自动加速单 Flow。
#. 多 Flow 未均匀分布时，应检查 RSS Hash、Indirection Table、Tunnel Inner Hash 和 Flow 分布。
#. Queue 数过多会增加 Ring、IRQ、内存、Cache 和管理成本，低流量 Queue 也可能浪费资源。
#. Worker 跨 NUMA 读取 UMEM 会增加 Remote Memory 延迟和互连流量。
#. NIC、CPU、UMEM 和下游 TX Queue 应尽量位于同一 NUMA Node，实际拓扑需用系统工具确认。
#. CPU Frequency、C-state、SMT 和 IRQ Sharing 会影响尾延迟，不能把所有波动归因于 BPF。
#. XDP Native、Generic 与 Hardware Offload 必须分别基准，运行位置不同导致 Counter 和 CPU 观察点也不同。
#. AF_XDP Copy 与 Zero-copy 必须确认实际模式，不能从配置意图推断。
#. Zero-copy CPU 高可能来自用户态 Parser、Cache Miss、Busy Poll 或跨 NUMA，而不是 Payload Copy。
#. 高吞吐测试应固定 Packet Size、Flow 数、方向、Burst、Queue、CPU 和 NUMA。
#. 单向大 Packet 吞吐测试不能代表双向小 Packet、连接建立或突发流量。
#. Benchmark 应先建立普通网络栈基线，再依次启用 Native XDP、Redirect、AF_XDP 和 Zero-copy。
#. 每个阶段只改变一个关键变量，并保留可回滚配置。
#. 输出至少包含 Packet/s、Gbit/s、CPU Core/Utilization、Cycles/Packet、P50/P99/P999、Drop 和错误率。
#. 只报告峰值 Packet/s 会掩盖 Drop、尾延迟、CPU 饱和和不可恢复状态。
#. 负载发生器也可能成为瓶颈，必须确认发送端 Queue、CPU、线速和抓包不会限制测试。
#. Wire Packet、NIC Counter、XDP Counter 和应用 Counter 的统计边界不同，数值不能未经换算直接要求相等。
#. GRO/GSO/TSO 会改变 Packet 计数粒度，XDP 通常位于 RX GRO 之前，应用可能看到聚合或流语义。
#. Hardware Offload 可让 Packet 在主机内核 Counter 之前处理，需同时读取设备侧统计。
#. Packet Drop 应按最早异常层级定位：Hardware Ring → Driver Refill → XDP Action/Redirect → Softnet → AF_XDP Ring → User Queue。
#. NIC ``rx_no_buffer`` 一类 Counter 增长通常先检查 RX Refill、UMEM/FILL 和 CPU 处理速度。
#. ``XDP_ABORTED`` 增长通常表示程序返回异常或 Helper/路径错误，应优先修复正确性。
#. Redirect Error 增长应检查目标 Map Entry、设备状态、Queue/Mode、Ring 空间和 Batch Flush。
#. AF_XDP Frame Leak 常表现为 FILL 逐渐减少、RX/TX 无法继续、总 Frame 数不守恒。
#. Verifier 接受但数据损坏，需检查 Header 修改、Checksum、UMEM Address、Length 和 Frame 重用。
#. IOMMU Fault 或 DMA 错误需检查驱动 Zero-copy、UMEM 生命周期、设备 Reset 和 Mapping 边界。
#. 程序替换或控制面重启时，应把 Counter Generation 与流量变化对齐，避免把 Counter Reset 误判为 Drop 消失。
#. Pin 的旧 Program/Map 可能让同一设备存在非预期策略，排障时应枚举所有 Link 和 Pin。
#. 优化不能牺牲故障恢复：Program Detach、Queue Reset、Worker Restart 和设备 Down/Up 必须可重复执行。
#. 用户 Worker 崩溃时，系统应能阻止新 Redirect、回收或重建 UMEM，而不是永久耗尽 Queue。
#. 控制面与数据面版本应通过 Map Schema、Generation 或 Pin Path 区分，避免新程序读取旧 Value 布局。
#. 安全策略更新应先准备新 Map/Program，再原子切换，最后回收旧对象。
#. 观测本身也有成本，长期生产方案应使用低成本 Counter、聚合和按需深度 Trace。
#. 最终优化顺序是：验证功能正确 → 定位最早 Drop → 定位最大 CPU → 对齐 Queue/NUMA → 调整 Batch/唤醒 → 再缩短程序。
#. 稳定源码阅读顺序是：Driver Counter/Queue → NAPI/XDP Hook → Program/Map → Redirect Core → XSK Ring → User Worker → TX/Completion → Reset/Teardown。

必背路径
--------

端到端计数链：

::

   NIC RX Packets
   → Driver/NAPI Processed
   → XDP PASS + DROP + TX + REDIRECT + ABORTED
   → Redirect Success / Error
   → AF_XDP RX Published
   → User RX Consumed
   → User TX Submitted
   → TX Completion Reaped

   每相邻两层的差值
   → 对应一个待解释的 Drop、Backlog 或统计边界

CPU 定位：

::

   /proc/interrupts 查看 IRQ CPU
   → /proc/softirqs 查看 NET_RX 压力
   → perf 查看 Driver/NAPI/BPF/User 热点
   → Map Counter 查看 Action 分布
   → Ring 指标查看等待位置
   → NUMA/CPU Affinity 检查远端访问
   → 只优化占比最大的已证明路径

AF_XDP Ring 故障：

::

   FILL 下降
   → 检查 Frame 是否从 RX 及时归还

   RX Ring 满
   → 检查 Worker 调度与 Batch

   TX Ring 满
   → 检查 Need-wakeup、驱动与 NIC

   Completion 积压
   → 检查用户回收循环

   总 Frame 不守恒
   → 检查 Double-submit、Leak 和提前复用

Queue/NUMA 对齐：

::

   确认 NIC NUMA Node
   → 确认 RX Queue 与 IRQ Vector
   → 设置 IRQ Affinity
   → 把 XSK Worker 绑定相同 CPU/Node
   → 在本地 Node 分配 UMEM
   → 确认 RSS Flow 分布
   → 比较 Cycles/Packet 与 P99

受控优化实验：

::

   保存基线配置和对象 ID
   → 固定流量与 Packet Size
   → 一次修改一个变量
   → 同时测 Throughput、CPU、P99、Drop
   → 验证 Counter 守恒和业务正确
   → 重复多轮并覆盖 Reset/Restart
   → 无稳定收益则恢复基线

必须区分
--------

策略 Drop 与资源 Drop
   XDP 策略拒绝可能是正确结果；Ring、Buffer 或 Queue 耗尽属于容量问题。

Verifier 拒绝与运行时瓶颈
   前者发生在加载阶段；后者发生在事件执行、Map、Redirect 或用户消费阶段。

IRQ 分布与完整 CPU 路径
   IRQ CPU 只是入口，RPS、NAPI、Worker 和 NUMA 可能让后续工作转移。

Ring 扩容与吞吐提升
   更大 Ring 只能吸收更多在途工作，也可能增加内存和排队延迟。

Counter 差值与真实丢包
   不同层统计粒度、Offload 和重置边界不同，必须先统一语义再计算差值。

一句话结论
----------

高性能 Packet Pipeline 的优化必须建立逐层守恒账本：先证明 Packet 在哪里消失、CPU 在哪里消耗、Frame 在哪里停留，再调整程序、Queue、NUMA、Batch 和唤醒策略。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 31，High Performance Networking XDP, eBPF, Zero Copy, and AF_XDP；
* AIBook 章节：Chapter 155，Observing and Optimizing High-Performance Packet Pipelines；
* 源文件：``docs/LinuxK/Part_31_High_Performance_Networking_XDP_eBPF_Zero_Copy_and_AF_XDP/Chapter_155_Observing_and_Optimizing_High_Performance_Packet_Pipelines.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_31_High_Performance_Networking_XDP_eBPF_Zero_Copy_and_AF_XDP/Chapter_155_Observing_and_Optimizing_High_Performance_Packet_Pipelines.md>`_。