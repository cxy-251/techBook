第153章：eBPF Program、Map、Verifier 与 Attach Point
===================================================

核心知识点
----------

eBPF 是受约束的内核扩展机制
   用户态提交字节码，内核依据 Program Type、Verifier 规则、Helper 白名单和 Attach Point 创建可执行对象；它不是任意代码直接以内核权限运行。

Program Type 定义静态合同
   Program Type 决定 ``R1`` Context 的类型、可访问字段、允许的 Helper、返回值和执行约束。XDP、TC、Tracepoint、Kprobe、LSM 与 Cgroup 程序不能互换解释。

Attach Point 定义运行位置
   Attach Point 决定程序由什么事件触发、位于哪条路径、执行频率和可观察信息。相同逻辑挂在不同 Hook 上会得到不同语义与性能。

Verifier 证明内存与控制流安全
   它跟踪寄存器类型、Scalar 范围、Pointer Base/Offset、NULL 状态、Stack 初始化和所有可达路径，并检查 Helper 参数及对象生命周期。

Verifier 不证明业务正确
   程序通过验证只表示低层访问满足安全模型，不表示过滤策略、并发更新、性能和故障处理正确。

Pointer 类型不能任意转换
   ``PTR_TO_CTX``、Packet Pointer、Map Value Pointer 和 Stack Pointer 各有访问边界。Packet 指针调整或 Helper 调用后常需重新建立范围证明。

Map 是独立共享对象
   Map Type 决定 Key/Value 组织、容量、并发、淘汰和 Per-CPU 语义。Hash、Array、LRU、LPM、DEVMAP、XSKMAP 与 Ring Buffer 解决不同问题。

Map Value 仍需并发协议
   Map 存在不代表复合字段更新自动原子。共享 Value 可能需要原子操作、锁或版本协议；Per-CPU Map 用空间换取低写竞争。

Program、Map、Link 和 Pin 分别持有引用
   关闭一个 fd 不一定释放对象；BPF Link、Attach 关系、其它进程和 bpffs Pin 都可能让对象继续存在。

CO-RE 解决布局适配而非能力适配
   BTF/CO-RE 可按目标内核重定位字段布局，但不能创造不存在的 Program Type、Helper、Attach Point 或语义。

热路径成本按事件频率放大
   Map Lookup、分支、Helper、共享写和事件输出在 Mpps 场景会显著放大。逐 Packet ``bpf_printk`` 不适合作为生产观测。

策略切换不是自动事务
   Program Replace 与多个 Map 更新之间可能存在短暂窗口，应通过 Link 原子替换、Generation、双 Map 或版本字段建立控制面协议。

关键路径
--------

Program 加载：

::

   用户态准备 ELF、BTF 与 Map 定义
   → 创建 Map Object
   → 选择 Program Type
   → BPF_PROG_LOAD 提交指令
   → Verifier 构建控制流并模拟状态
   → 检查 Pointer、Stack、Helper 和全部路径
   → 创建 Program Object
   → 可选 JIT
   → 返回 Program fd

Attach 与执行：

::

   选择 Attach Point
   → 创建 BPF Link 或子系统 Attach
   → Hook 持有 Program 引用
   → 事件发生并构造 Context
   → 执行 BPF/JIT 指令
   → 访问 Map / 调用 Helper
   → 返回值观察或改变后续路径

Map 状态：

::

   用户态创建并填充 Map
   → Program Lookup Key
   → 检查 NULL
   → 读取或更新 Value
   → 用户态聚合 Counter / 消费事件
   → 更新 Generation 或删除 Entry
   → 最后引用归零后释放 Map

安全替换：

::

   加载新 Program 与新 Map
   → 预填新策略
   → 原子 Replace Link
   → 验证新对象开始执行
   → 停止旧控制面写入
   → Detach 旧 Program
   → 删除旧 Pin
   → 等待旧引用结束

概念辨析
--------

* Program Type 与 Attach Point：前者定义 Context、Helper 和返回值；后者决定实际触发位置。
* Verifier 安全与业务正确：Verifier 证明低层访问规则，不证明策略逻辑和性能目标。
* Map fd 与 Map 生命周期：Fd 只是一个引用；Program、Link、Pin 或其它进程仍可持有对象。
* Per-CPU Map 与全局 Map：Per-CPU 降低共享写竞争，代价是更大内存和用户态聚合。
* CO-RE 与接口稳定：CO-RE 适配结构布局，不保证 Hook、Helper 和行为跨版本等价。

本章结论
--------

eBPF 的可编程性由 Program Type、Attach Point、Verifier、Helper 和 Map 生命周期共同约束；只有这些合同同时明确，扩展才可证明、可替换并可维护。
