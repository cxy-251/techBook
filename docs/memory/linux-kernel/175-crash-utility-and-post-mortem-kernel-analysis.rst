第175章：crash 工具与事后内核分析
================================

核心知识点
----------

``crash`` 读取冻结的内核世界
   Post-mortem 分析面对的是崩溃时刻的内存快照，不是崩溃前完整录像。时间顺序仍需日志、Tracepoint、序列号和复现补充。

Vmcore 与 Vmlinux 必须精确匹配
   ``vmcore`` 提供内存字节，带调试信息的 ``vmlinux`` 提供符号、类型和结构偏移。相同 Release 字符串不保证相同 Build。

基础自检先于对象推断
   应先确认 Architecture、Build ID、Page Size、KASLR、Config、Module 和 Dump Level，再用 ``sys``、``log``、``bt``、``ps`` 检查整体自洽性。

Panic Task 不一定制造了根因
   当前 Task 可能只是首先检测到损坏状态。Panic Stack 描述最后控制流，不能单独证明对象何时、由谁被破坏。

可靠调用栈有证据边界
   Exception、IRQ/NMI 和普通 Task Stack 可能交错；``?`` Frame、断裂 Unwind 和裸地址代表低置信度，必须结合寄存器、指令和源码验证。

多 CPU 与 Task 状态提供系统背景
   ``bt -a``、``ps``、``runq`` 等可观察其它 CPU、Runnable Task 和阻塞点。冻结状态不能说明持续时间，也不能把队列堆积直接归为调度器故障。

锁分析必须连接 Owner 与 Waiter
   栈中出现 ``mutex_lock``、``schedule`` 或 Spinlock Slowpath 只是等待入口。结论需要具体锁对象、持有者、等待者、临界区和持有者是否仍能运行。

地址可读不等于对象有效
   已释放 Slab 仍可能保留旧字段；不可读页面也可能是 Dump 过滤造成。地址必须放回 Direct Map、Vmalloc、Module、Slab、Page、MMIO 等区域解释。

对象分析依赖生命周期不变量
   Refcount、List、State、Owner、Ops、Parent、Generation 和异步工作状态应互相自洽。单个异常字段不足以证明 UAF 或内存破坏。

异步对象是常见失配点
   Workqueue、Timer、IRQ、RCU、Bio、Urb、Skb 和 DMA Descriptor 需要检查 Pending、Running、Completion 与宿主对象的 Remove/Release 顺序。

模块和外部驱动需要独立符号
   崩溃时实际加载的 ``.ko``、Debuginfo 和 Build ID 必须匹配。DKMS、模块重载和同名不同构建会让栈和私有结构解释失真。

结论应分层表达置信度
   报告应区分已证实事实、强支持推断、缺失页面或符号导致的不可确认部分，以及后续需要动态验证的假设。

关键路径
--------

打开 Dump：

::

   保留原始 Vmcore
   → 取得匹配 Vmlinux 与 Module Debuginfo
   → 校验 Release、Build ID、Architecture、Config 和 Dump Level
   → crash vmlinux vmcore
   → 用 sys / log / bt / ps 建立基础边界

还原失败路径：

::

   读取 Panic Reason 与 Fault Address
   → 确认当前 CPU 和 Task
   → 识别可靠 Stack Frame
   → 定位关键对象和访问指令
   → 检查其它 CPU、Task、锁和异步路径
   → 回到匹配源码验证失败条件

对象生命周期分析：

::

   取得对象地址与类型
   → 检查所属分配器和可见集合
   → 验证 Refcount、State、List、Owner 与 Generation
   → 检查最后 Put/Remove/Release
   → 检查 Worker、Timer、IRQ、RCU、DMA 是否仍引用
   → 建立 UAF、Double Free 或半初始化假设

概念辨析
--------

* Vmcore 与事件录像：Vmcore 保存冻结状态，不包含崩溃前全部时间顺序。
* Panic 位置与破坏位置：检测坏状态的函数可能远离最初写坏内存或提前释放对象的位置。
* 地址可读与对象存活：旧内存内容仍可读取，不代表对象仍处于合法生命周期。
* Refcount 与硬件可用性：引用可保护软件对象内存，不保证设备、连接或底层资源仍存在。
* 工具输出与证明：``crash`` 命令提供观察结果，结论仍需类型匹配、对象不变量和多源证据交叉验证。

本章结论
--------

``crash`` 的核心工作是用匹配符号和类型把 Vmcore 字节重建为 Task、Stack、Lock、Memory 与子系统对象，再通过控制流、对象状态和并发关系还原最后失败条件。