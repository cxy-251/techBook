第153章：eBPF Program、Map、Verifier 与 Attach Point
===================================================

本章必须记住
------------

#. eBPF 是受内核验证和类型约束的运行时扩展机制，不是任意用户代码直接以内核权限执行。
#. 完整生命周期是：创建 Map → 加载 Program → Verifier 检查 → 创建内核对象 → Attach → 事件触发执行 → Detach → 引用归零释放。
#. Program Type、Attach Point、Context、Helper 和返回值语义必须作为一个整体理解。
#. Program Type 在加载时决定 Verifier 如何解释 ``R1`` Context、允许哪些 Helper、允许访问哪些字段以及返回值合同。
#. Attach Point 在运行时决定程序位于哪条内核路径、由什么事件触发、执行频率和上下文约束。
#. 同样的业务逻辑挂在 XDP、TC、Socket、Cgroup、Tracepoint 或 Kprobe 上，会得到不同信息边界、性能和副作用。
#. XDP Program 看到 ``struct xdp_md``，通常返回 XDP Action；TC Program 看到 ``struct __sk_buff`` 并按 TC 语义返回。
#. Tracepoint Program 面向预定义事件上下文；Kprobe Program 面向函数入口或返回，稳定性通常更弱。
#. Cgroup Program 把策略绑定到 Cgroup 层级的 Socket、Connect、Device、Sysctl 等操作，具体类型持续演进。
#. ELF Section 名称帮助 libbpf 推断 Program Type 和 Attach 方式，最终边界仍由内核加载参数和 Link 决定。
#. ``SEC("xdp")`` 只是用户态对象文件中的加载线索，不代表程序已经成功挂载到目标设备。
#. 用户态通过 ``bpf()`` 系统调用或 libbpf 封装创建 Map、加载 Program、操作 Element 和创建 Link。
#. ``include/uapi/linux/bpf.h`` 是 BPF 用户 ABI 的重要入口，精确命令、类型和属性随内核演进。
#. Program 加载成功后形成内核 Program Object；Attach 成功后才会在目标事件上执行。
#. Program fd 是用户态引用句柄，关闭一个 fd 不一定销毁对象，因为 Link、Pin、Map 或其它引用可能继续持有。
#. BPF Link 把 Program 与 Attach Point 关系表达成独立内核对象，便于原子替换和生命周期管理。
#. 传统非 Link Attach API 仍广泛存在，具体 Detach 和替换语义依子系统与版本而定。
#. bpffs Pinning 为 Program、Map 或 Link 增加持久名称引用，使控制面退出后对象仍可存在。
#. Pinning 不是配置文件，它保留的是活动内核对象；过期 Pin 会让旧策略和资源继续存在。
#. BPF Map 是内核中的类型化共享存储对象，可由 BPF Program 和用户态控制面访问。
#. Map Type 决定 Key/Value 组织、并发语义、容量、淘汰策略、是否 Per-CPU 和可用 Helper。
#. Hash Map 适合按 Key 查找动态对象；Array 适合固定索引；Per-CPU Map 适合减少高频共享写竞争。
#. LRU Hash 能在容量受限时淘汰旧 Entry，淘汰本身会产生工作和状态丢失语义。
#. LPM Trie 适合最长前缀匹配；DEVMAP、CPUMAP、XSKMAP 用于特定网络 Redirect 目标。
#. Ring Buffer/Perf Event 等 Map 可把事件送到用户态，接口、排序和丢弃行为需要按目标类型验证。
#. Map-in-Map、Sockmap、Reuseport、Cgroup Storage 等类型具有专用语义，不能按普通 Hash Map 解释。
#. Map 的 ``max_entries`` 是硬容量合同之一，达到容量后 Update 可能失败、触发淘汰或覆盖，取决于 Map Type 和 Flags。
#. 用户态必须检查每次 Map Update/Delete/Lookup 返回值，不能假设控制面状态已成功进入数据面。
#. BPF Program 中的 Map Lookup 可能返回 NULL，Verifier 要求在解引用前建立非空分支。
#. Hash Map Entry 的并发更新需要理解 Value 内部同步；Map 存在不等于复合字段更新自动原子。
#. Per-CPU Map 让每 CPU 更新独立 Value，用户态读取时需要聚合所有可能 CPU 的副本。
#. Per-CPU 结构减少共享 Cache Line 竞争，也会增加总内存和读取聚合成本。
#. Map Value 指针只在当前程序执行和 Map 合同允许的范围内有效，不能长期保存为普通内核指针。
#. Map Entry 删除、更新和 RCU 生命周期由 Map 实现管理，程序只能通过允许的 Helper 访问。
#. Verifier 在加载时分析控制流、寄存器状态、栈、指针类型、边界和 Helper 调用。
#. Verifier 接受的是可证明满足其安全模型的字节码，不是对业务正确性、性能或安全策略的认证。
#. 程序初始 ``R1`` 通常是 ``PTR_TO_CTX``；不同 Program Type 提供不同 Context Access 规则。
#. Verifier 跟踪 Scalar 的可能取值范围、Pointer Base、Offset、NULL 状态和对象类型。
#. ``PTR_TO_PACKET``、``PTR_TO_PACKET_END``、``PTR_TO_MAP_VALUE``、``PTR_TO_STACK`` 等类型不能任意互换。
#. Packet Pointer 访问必须由此前的 Data-end 检查证明范围，检查后修改 Pointer 时可能需要重新建立证明。
#. Map Lookup 的结果是 Nullable Pointer，判空后才会收窄为可解引用 Map Value Pointer。
#. Stack 空间必须先写后读，未初始化 Stack Byte 会导致加载拒绝。
#. Helper 参数必须符合 Prototype，包括 Pointer 类型、长度、Flags、可写性和对象生命周期。
#. Program Type 只允许调用相应 Helper 集合；某个 Helper 在另一类型可用不表示当前程序可用。
#. Verifier 会遍历可达控制流并要求所有路径都安全，隐藏在错误分支中的越界访问同样会被拒绝。
#. 现代内核支持受证明有界的 Loop；Loop 迭代上界过大仍会增加验证复杂度和运行成本。
#. Verifier 状态爆炸常来自复杂分支、宽范围循环、难以收窄的 Pointer 和重复状态组合。
#. 将逻辑拆成小 Helper、明确边界、缩小变量范围和减少不必要分支，通常比盲目提高限制更可靠。
#. Tail Call 允许从一个 BPF Program 跳转到 Program Array 中的另一个 Program，调用深度和状态传递受约束。
#. BPF-to-BPF Function Call 与 Tail Call 是不同机制，栈和调用边界也不同。
#. Verifier Log 是加载失败的首要证据，应从第一处状态不满足位置读取，而不是只看最终“permission denied”。
#. ``EPERM``、``EINVAL``、``E2BIG`` 等加载错误可能来自权限、Verifier、属性、指令或内核能力不同，需结合 Log 判断。
#. Program 通过 Verifier 后可由 JIT 编译为本机指令，也可按配置走解释执行或其它模式。
#. JIT 提高运行效率，不改变 Program Type、Helper 和 Map 的安全合同。
#. JIT 状态、Hardening、Kallsyms 和统计暴露受内核配置、安全策略和权限限制。
#. BTF 描述内核和 BPF 对象类型信息，可用于 CO-RE Relocation、Typed Context 和更稳定的工具输出。
#. CO-RE 通过 BTF 在加载时适配字段布局，不能保证目标内核拥有相同 Helper、Program Type 或 Attach Point。
#. Kprobe 依赖具体符号和函数实现，内核升级时比 Tracepoint、LSM 或正式 BPF Hook 更容易变化。
#. Tracepoint 字段也可能演进，但它是显式观测接口，通常比任意函数探测边界更清晰。
#. Attach 越靠近热路径，Program 每次执行的预算越严格；高频 XDP/TC 路径应避免复杂 Map、全局锁和逐事件输出。
#. 使用共享 Hash Map 做全局计数可能让所有 CPU 争用同一 Cache Line。
#. 使用 ``bpf_printk`` 做逐 Packet 日志会严重扰动系统，只适合低频受控调试。
#. Ring Buffer 事件也会占用内存和用户态消费能力，Buffer 满时可丢事件或使 Reserve 失败。
#. 观测 Program 必须把“未采集到事件”和“事件没有发生”区分开。
#. Program 返回值可以直接改变 Packet、Security 或 Cgroup 路径，因此加载和 Attach 权限属于系统安全边界。
#. BPF 权限模型受 Capability、Unprivileged BPF 配置、LSM、Lockdown、Namespace 和发行版策略影响。
#. 容器中可见 bpffs 或 BPF fd 不自动获得对宿主 Hook 的 Attach 权限。
#. Map 中的策略数据也属于安全输入，用户态控制面必须验证 Key、Value、版本和更新权限。
#. BPF Object 可被多个进程共享；没有单一“拥有者进程”时，必须用 Pin/Link 与控制面协议管理更新。
#. 原子替换 Program 时应指定预期旧 Program/Link，避免多个控制面互相覆盖。
#. 更新 Map 与替换 Program 的顺序会产生短暂策略窗口，应设计 Generation、双 Map 或原子切换协议。
#. Detach Program 不自动删除 Map；删除 Map Pin 也不保证没有 Program 或 fd 继续引用。
#. Teardown 应先停止新控制面更新，再 Detach/Replace Program，等待在途执行安全结束，最后释放 Link、Program、Map 和 Pin。
#. RCU 和对象引用保证 Program/Map 内核生命周期，不等于业务策略切换在多对象之间自动事务化。
#. ``bpftool prog show``、``map show``、``link show`` 用于确认对象存在、类型、ID、Tag、引用和部分 Attach 状态。
#. bpftool 输出字段随内核和工具版本变化，Program ID 也可能在对象释放后被重新使用。
#. 可靠关联应同时使用对象 ID、Tag、Pin Path、Link 和业务 Generation，而不是只记录一个 ID。
#. Verifier 拒绝属于加载阶段；运行期 Map 满、Helper 失败、Redirect 失败和 Ring 满属于执行阶段。
#. Program 加载成功但无事件，常见原因是 Attach Point 错、Namespace/设备错、流量未经过该 Hook 或被更早路径处理。
#. Program Counter 增长但业务无效果，需检查返回值、Map 内容、目标对象和后续路径是否覆盖结果。
#. 性能分析要把 BPF JIT 指令、Map Lookup、Helper、目标子系统和用户态控制面分别观察。
#. 稳定源码阅读顺序是：UAPI ``bpf()`` 属性 → Map/Program 创建 → Verifier Ops → Program Type Context → Attach/Link → Hook 执行 → Map/Helper → Detach/引用释放。

必背路径
--------

Program 加载：

::

   用户态准备 ELF、BTF 和 Map 定义
   → 创建 BPF Map
   → 选择 Program Type
   → BPF_PROG_LOAD 提交指令与属性
   → Verifier 构建 CFG 并模拟状态
   → 检查 Context、Pointer、Stack、Helper 和所有路径
   → 通过后创建 Program Object
   → 可选 JIT 编译
   → 返回 Program fd

Attach 与运行：

::

   选择目标 Attach Point
   → 创建 BPF Link 或执行子系统 Attach
   → 内核持有 Program 引用
   → 目标事件发生
   → 按 Program Type 构造 Context
   → 执行 BPF/JIT 指令
   → 调用受限 Helper / 访问 Map
   → 返回值影响或观察后续路径

Map 共享状态：

::

   用户态创建 Map
   → Program 持有 Map 引用
   → 用户态写入策略 Entry
   → Program Lookup Key
   → 判空并读取/更新 Value
   → 用户态读取 Counter/事件
   → 更新、删除或切换 Generation
   → 最后引用归零后释放 Map

Verifier Pointer 证明：

::

   从 Context 取得 Packet/Map Pointer
   → 检查可能为 NULL
   → 检查 data + required <= data_end
   → Verifier 收窄 Pointer 状态
   → 只访问已证明范围
   → Helper 或 Pointer 调整后重新验证

安全替换：

::

   构建并验证新 Program/Map
   → 预填新策略状态
   → 原子 Replace Link 或 Attach
   → 确认新 Program Counter 增长
   → 停止旧控制面更新
   → Detach 旧 Program
   → 删除旧 Pin
   → 等待引用结束并释放旧对象

必须区分
--------

* Program Type 与 Attach Point：Program Type 定义 Context、Helper 和返回值；Attach Point 决定实际触发位置。
* Verifier 安全与业务正确：Verifier 证明低层访问满足规则，不证明过滤策略、计数或并发逻辑正确。
* Map fd 与 Map 生命周期：Fd 是一个引用；Program、Link、Pin 或其它进程仍可让 Map 继续存在。
* Per-CPU Map 与全局 Map：Per-CPU 写入减少共享竞争，读取必须聚合；全局 Map 便于共享，可能产生同步热点。
* 加载失败与运行期失败：Verifier 拒绝发生在对象创建前；Map 满、Redirect 失败和 Helper 返回错误发生在事件执行时。

一句话结论
----------

eBPF 的可编程性由类型化 Hook、Verifier、受限 Helper 和 Map 生命周期共同约束；只有 Program Type、Attach Point、共享状态和对象引用全部明确，扩展才是可证明且可维护的。
