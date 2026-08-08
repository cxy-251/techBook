第059章：Runtime Design, Battery, Memory, Responsiveness
=======================================================

核心知识点
----------

* Runtime design 不是追求单点最快，而是在 CPU、内存、存储、启动时间、电池和温控之间维持稳定响应。
* 前台同步工作决定用户等待与帧稳定；JIT、profile、缓存修剪、对象释放等后台工作决定额外 CPU、存储写入和能耗。
* GC 与 ARC 都管理对象生命周期，但压力形态不同：GC 更关注分配速率、可达性、回收暂停与并发竞争；ARC 更关注 retain/release、autorelease、强引用环与集中释放。
* JIT 用运行时 CPU、code cache 与 profile 换取真实热路径优化；AOT 用安装、更新或后台编译成本与存储换取更低运行时开销。
* Runtime cache 可以缩短启动和恢复，但缓存越重，进程在系统内存压力下越容易失去驻留优势。
* Runtime failure 常见表现包括 crash、OOM、deadlock、startup timeout、主线程卡死与 native memory corruption，必须按证据类型定位。
* Runtime 与生命周期策略相交：系统最终会根据前后台状态、内存压力、功耗和热预算决定进程继续保留、降级还是被回收。

关键路径
--------

资源消耗链：

``App 行为 → Runtime 加载 / 执行 → CPU + Allocation + Cache → GC / ARC + JIT / AOT → System Pressure → 保留 / 降级 / 回收``

典型用户路径：

``Cold Start → Runtime Init → First Frame → Scroll / Allocation → Cache Growth → Background → Memory Pressure Decision → Resume 或 Next Cold Start``

排查顺序：

#. 启动慢先查 code loading、编译状态、静态初始化和主线程同步工作。
#. 滚动卡顿再看 allocation rate、GC / ARC 活动、图片解码和 frame deadline。
#. 内存不降时检查 retained object、reference cycle、autorelease、native allocation 和 cache ownership。
#. 耗电异常时看持续 CPU、频繁 JIT / retry、后台任务、唤醒和热降频是否重叠。
#. 后台返回变慢时确认进程是保留、冻结还是已经被系统回收。

概念辨析
--------

* **GC Pause 与 Memory Leak**：GC pause 是回收过程造成的执行影响；leak 是对象仍被引用或资源未释放，二者不是同一问题。
* **ARC 与 自动无泄漏**：ARC 自动插入引用计数操作，但强引用环、闭包捕获和不当 ownership 仍可保留对象。
* **JIT 与 AOT**：两者都生成机器码，只是把编译成本放在不同时间点。
* **Runtime Cache 与 Process Cache**：前者是类、代码、对象等运行时缓存；后者是系统保留整个 App process 以便快速恢复。
* **OOM 与 系统回收**：应用自身 OOM 是当前进程无法满足内存需求；系统回收是平台主动终止低优先级进程以维护全局资源。

本章结论
--------

Runtime 是 App experience 与 system resource policy 的交汇层。性能判断不能只看执行速度，还要同时看对象生命周期、编译成本、缓存规模、前后台状态和系统回收结果；稳定目标是让用户可见路径足够轻，同时把可延后工作交给更合适的时间和系统预算。