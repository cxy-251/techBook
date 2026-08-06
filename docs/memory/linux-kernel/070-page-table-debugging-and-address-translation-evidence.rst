第070章：页表调试与地址转换证据
================================

核心知识点
----------

虚拟内存问题必须分层取证
   一个地址异常至少涉及地址值、VMA 范围策略、页表项状态以及物理页、文件页或 swap 后端。直接从地址跳到“内存坏了”会混淆完全不同的故障层次。

``maps`` 先回答范围与权限
   ``/proc/<pid>/maps`` 显示当前 VMA 的地址范围、读写执行权限、文件偏移和后端来源。它能判断地址是否属于某个映射，但不能证明其中每一页已经驻留。

``smaps`` 补充驻留与共享统计
   ``Size`` 表示虚拟范围，``Rss`` 表示当前驻留量，``Pss`` 按共享者比例分摊共享页。匿名页、文件页、私有脏页和 swap 等字段用于解释内存实际由什么组成。

``pagemap`` 提供页级状态
   每个虚拟页对应一条记录，可表达 present、swapped、soft-dirty 等信息。字段含义和 PFN 可见性具有版本与权限约束，必须按目标内核文档解释。

PFN 不可见不等于页面不存在
   现代内核通常限制普通用户读取真实 PFN。PFN 为 0 可能来自权限屏蔽、零页或其它情况，必须与 present 位、权限环境和内核版本联合判断。

Page fault 可以是正常路径
   匿名首次分配、COW、page cache 命中和 swap 换入都会触发 fault。Minor fault 不需要慢速存储 I/O；major fault 需要文件或 swap I/O，二者只有在频率和延迟异常时才构成性能问题。

SIGSEGV 需要区分映射与权限错误
   ``si_addr`` 给出故障地址。``SEGV_MAPERR`` 通常表示没有覆盖地址的 VMA，``SEGV_ACCERR`` 通常表示映射存在但访问方式违反权限；最终仍要结合架构错误码和故障指令确认。

Procfs 证据是瞬时视图
   目标进程可能同时执行 ``mmap``、``munmap``、``mprotect``、缺页和回收。单次 ``maps``、``smaps`` 或 ``pagemap`` 读取不能自动形成稳定时间线。

可靠结论需要多源交叉验证
   VMA、页表、fault 计数、信号信息、反汇编、trace 和源码分别回答不同问题。最终结论应明确故障发生在范围缺失、权限、页面驻留、I/O、COW、TLB 或对象生命周期中的哪一层。

关键路径
--------

分析一个故障地址：

::

   记录 PID、故障地址与访问类型
   → 在 maps 中查找覆盖范围
   → 无 VMA 时判断映射缺失
   → 有 VMA 时检查 r/w/x 权限
   → 用 smaps 判断驻留量与后端分类
   → 必要时读取 pagemap 的 present / swapped 状态
   → 对照 siginfo、fault 类型与故障指令
   → 回到缺页或权限处理源码

读取 pagemap：

::

   获取目标系统 page size
   → 虚拟地址除以 page size 得到虚拟页号
   → 乘 8 得到 pagemap 文件偏移
   → 读取对应 8 字节记录
   → 按目标内核解析 present、swapped 与其它标志
   → 检查当前权限是否允许查看 PFN
   → 必要时关联 kpageflags 与 kpagecount

区分 minor 与 major fault：

::

   CPU 触发 page fault
   → 查找 VMA 并验证权限
   → 匿名分配、COW 或 page cache 命中
   → 不需要存储 I/O，记录 minor fault
   或文件页、swap 内容不在内存
   → 执行 I/O 并建立映射
   → 记录 major fault

分析 SIGSEGV：

::

   保存 si_addr、si_code 与寄存器现场
   → maps 判断地址是否有映射
   → 无映射时检查越界、悬空指针和并发 munmap
   → 有映射时检查写入、执行或用户权限
   → 对照反汇编确定故障指令
   → 检查页表、TLB 与对象释放时间线

概念辨析
--------

VMA 存在与页面 present
   VMA 表示地址范围合法且有策略；present 表示某个具体虚拟页当前已有可用页表映射。

虚拟大小、RSS 与 PSS
   Size 是保留范围，RSS 是当前驻留量，PSS 是共享页按共享者比例分摊后的贡献。

Minor fault 与 major fault
   Minor 不需要慢速存储 I/O；major 需要文件或 swap I/O。

``SEGV_MAPERR`` 与 ``SEGV_ACCERR``
   前者通常表示映射缺失；后者通常表示映射存在但访问权限不允许。

PFN 为 0 与页面不存在
   PFN 可能被权限策略隐藏，必须结合 present、内核版本和权限环境解释。

瞬时采样与故障时间线
   Procfs 只能描述读取附近的状态；并发映射变化和短暂 fault 需要 trace、信号现场或连续采样补充。

本章结论
--------

页表调试应按“地址 → VMA → 页表项 → 页面后端 → fault 结果”逐层收集证据。任何单个 RSS、PFN、fault 计数或 SIGSEGV 都不足以独立说明根因。