第五十六章：Linux 怎样准备 Maple Tree、文本热补丁和 ftrace？
============================================================

第五十五章结束时，普通可用 RAM 已从 memblock 交给 buddy，slab 与 vmalloc 基础也已经建立。

``start_kernel()`` 接下来连续执行：

.. code-block:: c

   maple_tree_init();
   poking_init();
   ftrace_init();
   early_trace_init();

本章追踪到 ``early_trace_init()`` 返回，停在 ``sched_init()`` 之前。

这四个函数看起来分属不同领域，实际共享一个启动条件：它们都需要正式内存分配器已经可用，同时必须赶在调度器、中断和多 CPU 并发真正展开之前，先建立运行期会反复使用的基础设施。

为什么 Maple Tree 要等 slab 可用
--------------------------------

Maple Tree 是 Linux 用来保存“整数索引或整数范围 → 对象指针”映射的范围树。

它最重要的使用者之一是进程地址空间。现代内核中的 ``mm_struct`` 使用 Maple Tree 管理 VMA：

.. code-block:: text

   virtual address range
       → vm_area_struct

例如：

.. code-block:: text

   0x400000 - 0x40ffff   → executable mapping
   0x600000 - 0x60ffff   → writable data
   0x7f...   - 0x7f...   → shared library

Maple Tree 节点不是固定放在某个全局数组中。树增长、分裂或重平衡时需要动态分配 ``struct maple_node``。

所以 ``maple_tree_init()`` 的关键工作是为 Maple Tree 节点建立专用 slab cache：

.. code-block:: text

   maple_node_cache
       → fixed-size maple_node objects
       → kmem_cache allocation

第五十五章的 ``kmem_cache_init()`` 完成前，内核还不能可靠创建这个运行期 cache。

这里没有创建任何用户进程 VMA
---------------------------

``maple_tree_init()`` 只准备节点分配器。

当前尚未发生：

* 创建 PID 1 的 ``mm_struct``；
* 映射 ELF 用户程序；
* 执行 ``mmap()``；
* 建立共享库 VMA；
* 处理 page fault。

此时仍只有内核启动任务 ``init_task``，它使用 ``init_mm``，没有普通用户地址空间。

Maple Tree 被放在这里，是因为后面的 fork、exec、VMA、procfs 和其他范围管理代码需要它已经可用。

Maple Tree 与 radix tree 不是同一个结构
--------------------------------------

``maple_tree_init()`` 之后不久还会看到 ``radix_tree_init()``。

二者服务重点不同：

``Maple Tree``
   擅长保存连续范围，能够直接表达 ``start..end`` 对应同一对象，适合 VMA 与地址区间。

``XArray / radix tree 基础``
   更常用于按离散整数索引保存对象，例如页缓存中的 page/folio index。

因此当前初始化 Maple Tree，并不代表旧的 radix tree/XArray 路径已经消失。

为什么运行中的内核代码需要被修改
--------------------------------

下一条调用是：

.. code-block:: c

   poking_init();

Linux 内核的 ``.text`` 区在最终状态下应当只读且可执行，不能长期保持可写。

但内核运行期间又确实需要修改少量指令，例如：

* static key / jump label；
* static call；
* dynamic ftrace；
* kprobes；
* livepatch；
* alternatives 或安全缓解路径的动态切换。

这类修改通常称为 text poking。

目标不是把整个内核 text 改成 RWX，而是建立一个受控过程：

.. code-block:: text

   选择少量目标指令
   → 建立临时可写访问方式
   → 写入经过验证的新 opcode
   → 同步 instruction stream / TLB / CPU
   → 撤销临时写权限或映射

``poking_init()`` 为 x86 的运行期 text patching 准备架构环境。

它不在这里修改一批具体指令
--------------------------

前面的启动阶段已经执行过 alternatives、jump label 和 static call 的早期 patch。

当前 ``poking_init()`` 主要建立后续 ``text_poke*()`` 路径所需的安全修改基础。真正的目标地址和新指令会由 ftrace、kprobe、static key 等调用者在以后提交。

所以它不是：

.. code-block:: text

   再次扫描并重写整个 vmlinux

而是：

.. code-block:: text

   让以后能够在严格 W^X 约束下修改少量内核指令

为什么 text patching 必须考虑正在执行的 CPU
-----------------------------------------

修改数据与修改机器指令不同。

若一个 CPU 正在执行目标指令，另一个执行上下文同时覆盖其字节，CPU 可能观察到旧指令和新指令的混合状态。

x86 的运行期 patching 因此可能使用：

* 临时 ``INT3`` 断点字节；
* 分阶段替换指令尾部和首字节；
* instruction synchronization；
* 跨 CPU 同步；
* patch 期间的异常处理路径。

当前只有 CPU0 online，尚未启动 AP，环境相对简单。但 ``poking_init()`` 建立的机制必须能在以后 SMP 已运行时继续安全工作。

``ftrace_init()`` 准备的不是 tracefs 界面
---------------------------------------

下一条调用：

.. code-block:: c

   ftrace_init();

ftrace 的函数跟踪基础来自编译器和链接器预先放入内核映像的信息。

根据构建方式，函数入口附近可能存在：

.. code-block:: text

   mcount
   __fentry__
   architecture-specific patchable call site

链接器还会形成一组可定位这些 call site 的记录。

``ftrace_init()`` 读取这些位置，为内核核心 text 建立 ``dyn_ftrace`` 等运行期记录，使以后能够按函数选择启用或停用跟踪。

默认情况下不能让每个函数入口都执行昂贵 tracer
----------------------------------------------

若所有编译出的 ftrace call site 从启动开始都调用通用 tracer，开销会非常大，而且 tracer 自身尚未完整初始化。

dynamic ftrace 的基本思路是：

.. code-block:: text

   tracing disabled
       call site → NOP / inactive form

   tracing enabled for selected function
       call site → ftrace trampoline

   tracing disabled again
       call site → NOP / inactive form

这种切换依赖刚刚准备好的 text-poking 机制。

``ftrace_init()`` 因此连接了两层：

.. code-block:: text

   compiler/linker generated call-site metadata
       ↓
   runtime ftrace records
       ↓
   safe instruction patching

这里仍没有开始记录全部函数
--------------------------

当前函数返回后，ftrace 核心已经知道哪些内核函数入口可被跟踪。

它不等于：

* function tracer 已经全局开启；
* ring buffer 已经记录所有调用；
* ``tracefs`` 已经挂载；
* ``/sys/kernel/tracing`` 已经可访问；
* 用户空间已经选择 tracer/filter。

是否在启动期启用某个 tracer，还取决于构建配置和命令行，例如 ``ftrace=``、``ftrace_filter=``、``trace_event=`` 等相关选项。

``early_trace_init()`` 为什么放在 scheduler 前
--------------------------------------------

接下来：

.. code-block:: c

   early_trace_init();

此时已经具备：

* buddy/slab/vmalloc；
* per-CPU area；
* text patching；
* ftrace call-site 表；
* printk ring buffer。

但仍没有：

* 完整 scheduler；
* 普通中断；
* tracefs 文件系统接口；
* 用户态控制程序。

``early_trace_init()`` 处理能够在这个阶段建立的 tracing 基础，并让通过启动参数请求的早期 tracing 尽可能覆盖随后发生的 scheduler、IRQ 和 timer 初始化。

如果等到所有子系统完成后才启用 tracing，就无法观察最需要诊断的启动过程。

``trace_printk`` 与普通 printk 不相同
-----------------------------------

源码在调用前特别说明：

.. code-block:: c

   /* trace_printk can be enabled here */

``trace_printk()`` 把调试记录写入 tracing ring buffer，适合开发和定位内核时序问题。

普通 ``printk()`` 写入 printk ring buffer，最终由 console 或 ``/dev/kmsg`` 消费。

二者具有不同的 buffer、格式和使用目的。当前 ``early_trace_init()`` 不会取代已经建立的 printk 系统。

为什么 tracing 要早于 scheduler
-----------------------------

下一入口是 ``sched_init()``。

调度器初始化会建立 runqueue、idle task 关系、调度类状态和 preemption 模型。如果 tracing 在它之后才有最早基础，就难以观察这段初始化以及后续第一次任务切换。

因此顺序形成清晰依赖：

.. code-block:: text

   buddy/slab/vmalloc
   → Maple Tree node cache
   → safe text poking
   → ftrace call-site records
   → early tracing
   → scheduler

本章结束时发生了什么变化
------------------------

本章之前，正式 allocator 已可用，但一些即将被运行期核心代码使用的数据结构和代码修改工具还没有准备。

本章之后：

* Maple Tree 节点可以从专用 slab cache 分配；
* x86 具备受控的运行期 text-poking 基础；
* ftrace 已建立核心内核函数 call-site 元数据；
* 条件 early tracing 可以覆盖后续启动阶段。

这些能力还没有让 CPU0 切换到另一个任务。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``early_trace_init()`` 已返回，``sched_init()`` 尚未调用；
* CPU：只有 CPU0 online；
* current task：``init_task``；
* interrupts：关闭；
* buddy/slab/vmalloc：可用；
* Maple Tree：节点 cache 已建立；
* text poking：x86 运行期安全补丁环境已准备；
* ftrace：核心 call-site 元数据已建立；
* tracing：早期条件初始化已执行；
* scheduler：尚未初始化；
* AP：尚未收到 INIT/SIPI；
* initramfs：尚未解包；
* PID 1：尚未创建。

下一条控制流是：

.. code-block:: c

   sched_init();

下一章将解释 scheduler 初始化究竟建立了什么，以及为什么 ``sched_init()`` 返回并不表示系统已经发生第一次任务切换。

资料
----

* `Linux 6.12.95 init/main.c：Maple Tree、poking、ftrace、early trace 与 sched_init 顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 6.12.95 lib/maple_tree.c：Maple Tree 节点与初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/lib/maple_tree.c>`_
* `Linux 6.12.95 arch/x86/kernel/alternative.c：x86 text poking 与指令同步 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/alternative.c>`_
* `Linux 6.12.95 kernel/trace/ftrace.c：dynamic ftrace call-site 管理 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/trace/ftrace.c>`_
* `Linux 6.12.95 kernel/trace/trace.c：early_trace_init 与 tracing 基础 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/trace/trace.c>`_
* `Linux Maple Tree 文档 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/core-api/maple_tree.rst>`_
* `Linux ftrace 文档 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/trace/ftrace.rst>`_