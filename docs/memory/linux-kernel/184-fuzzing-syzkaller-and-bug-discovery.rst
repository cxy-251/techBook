第184章：Fuzzing、syzkaller 与缺陷发现
=====================================

核心知识点
----------

内核 Fuzzing 探索未规划状态
   Fuzzer 通过自动生成、变异和组合输入，持续探索人工测试未覆盖的边界值、调用顺序、对象生命周期和并发窗口。

深层覆盖依赖资源语义
   纯随机 Syscall Number、fd 和指针通常停在浅层校验。有效输入必须先创建 File、Socket、Mount、VMA、BPF Map 等资源，再变异其长度、Flag、顺序和释放时机。

Syscall 序列是一段状态程序
   每个调用既消费旧状态，也可能生产后续调用需要的资源。分析 Reproducer 时，应先找资源创建，再找状态转换，最后定位触发报告的调用。

攻击面由可达性与状态复杂度共同决定
   Syscall、Ioctl、Netlink、BPF、Filesystem、Procfs 写入口和设备节点的风险，不只取决于入口数量，还取决于权限、长期状态、异步行为和对象组合能力。

Coverage 是探索反馈
   KCOV 等机制告诉 Fuzzer 哪些路径被执行，并帮助保留能产生新覆盖的输入。新 Coverage 不是缺陷证据，只是进一步变异的方向。

Bug Oracle 决定何时报告
   KASAN、KCSAN、Lockdep、WARN、Oops、Hang、Leak 和行为差异把异常执行转换成可观察信号。首个违规报告通常比后续 Panic 更接近根因。

syzkaller 使用声明式系统调用模型
   Syscall、Struct、Flag、Resource 和方向关系的描述，使生成器能够构造足够合法的程序，并围绕真实对象依赖进行覆盖引导变异。

Corpus 保存有价值的状态程序
   能进入新路径或触发重要行为的程序进入 Corpus，后续通过参数修改、调用插入删除、并发和重复继续扩展状态空间。

Reproducer 收缩随机发现
   ``repro.syz`` 保留 syzkaller 的资源和执行语义；C Reproducer 更便于独立阅读，但可能无法表达 Executor、Sandbox、并发或故障注入条件。

复现概率属于报告内容
   竞态、CPU 数、虚拟化、调试配置和内存布局会影响触发率。应记录成功次数、总次数、Commit、Config、Architecture 和 Sandbox，而不是只写“可复现”。

专用子系统需要语义化输入
   Filesystem Image、BPF Program、Netlink Attribute、Packet Sequence、Driver Ioctl 和设备状态具有复杂结构，随机字节不足以稳定进入深层路径。

修复必须回到对象协议
   Use-after-free、数据竞争和锁告警应沿 Alloc、Publish、Use、Remove、Free 或同步关系分析，不能只删除 WARN、改变时序或屏蔽检测器。

关键路径
--------

Coverage-guided Fuzzing：

::

   UAPI / Syscall Description
   → 生成或变异 Program
   → Executor 在目标内核运行
   → KCOV 返回 Coverage / Comparison
   → 新路径进入 Corpus
   → Sanitizer / WARN / Crash 触发
   → 最小化 Reproducer
   → 根因分析与回归固定

Reproducer 阅读：

::

   固定 Commit / Config / Architecture
   → 读取 Sandbox 与执行选项
   → 找资源生产调用
   → 找对象状态转换
   → 找并发、重复和释放窗口
   → 对齐首个失败栈
   → 重建对象生命周期

缺陷修复闭环：

::

   Fuzz 报告
   → 确认首个违规信号
   → 稳定最小 Reproducer
   → 定位所有权或同步缺口
   → 修复对象不变量
   → 运行旧 Reproducer 与相关 Corpus
   → 增加 KUnit / kselftest / Fuzz Regression

概念辨析
--------

* **随机输入与语义化探索**：随机字节常被浅层校验拒绝；语义化 Fuzzing 先构造有效资源，再探索异常状态组合。
* **Coverage 与 Bug**：Coverage 证明路径被执行；Sanitizer、Crash、Hang 或错误行为才构成缺陷信号。
* **Crash 标题与根因**：标题用于聚类；根因需要首个违规证据、对象生命周期和稳定复现共同支持。
* **``repro.syz`` 与 C Reproducer**：前者保留 syzkaller 执行语义，后者便于独立阅读但表达能力可能更弱。
* **最后触发调用与最初破坏点**：崩溃调用可能只暴露早先已经损坏的对象，根因常发生在更早的并发或释放路径。
* **报告消失与正确修复**：配置、时序和路径变化也会让报告消失；只有对象不变量恢复并通过回归验证才算修复。

本章结论
--------

Fuzzing 的核心是用资源感知的状态程序和覆盖反馈探索未规划内核路径，再把随机发现压缩成可重复、可解释、可永久回归的对象级缺陷证据。
