第五十六章：Linux 怎样准备 Maple Tree、text poking 与 early tracing？
=====================================================================

第五十五章结束时，buddy、SLUB与vmap基础可用，CPU0仍在 ``start_kernel``、IF=0；scheduler尚未建立。
当前连续入口是：

.. code-block:: c

   maple_tree_init();
   poking_init();
   ftrace_init();
   early_trace_init();

本章按fixed Linux 7.2-rc1追踪四项返回。它先建立Maple node cache，再为x86受控text patch预建专用
``mm_struct`` 与PTE，随后按build建立dynamic-ftrace location records和early trace buffers/events。
这里没有创建用户VMA、没有任意RWX mapping，也没有发生task switch。

Maple Tree call只创建一个fatal-on-failure cache
---------------------------------------------

``maple_tree_init`` 以 ``sizeof(struct maple_node)`` 同时作为object size和alignment，设置SLUB sheaf
capacity 32，再 ``kmem_cache_create("maple_node",...,SLAB_PANIC)``。055必须先让SLUB可用；allocation
失败会panic而无正常出口。

该cache供later Maple trees在range split/grow时取nodes。此处没有创建PID 1 ``mm_struct``、没有向
``init_mm`` 加VMA，也没有page fault/mmap。Maple Tree的range mapping用途与058仍会初始化的离散
radix/XArray基础不能合并。

x86 text-poke 使用专用mm而非把kernel text常驻RWX
-----------------------------------------------

``poking_init`` 先 ``mm_alloc`` 创建 ``text_poke_mm``，失败 ``BUG_ON``；paravirt hook可为Xen PV pin
PGD，随后 ``set_notrack_mm`` 排除context tracking。它从 ``TASK_UNMAPPED_BASE`` 选临时user-range
address；KASLR build加入 ``kaslr_get_random_long("Poking")`` offset，并调整使连续两页不跨PMD boundary。

``get_locked_pte`` 立即为该address分配所需page-table levels并取得PTE lock，确认成功后只unlock；当前
PTE仍没有映入某段kernel text。预分配是因为later text poke可发生在atomic context，届时不能依赖会
sleep/fail的page-table allocation。

later patcher才会临时把target text page alias到这两页，执行受控opcode replacement和instruction/
TLB synchronization，再撤销alias。 ``poking_init`` 本身不扫描vmlinux、不修改jump label/ftrace site，
也不把整个 ``.text`` 设为writable。

dynamic ftrace先把linker locations变成runtime records
-----------------------------------------------

支持dynamic function tracing的build中， ``ftrace_init`` 在 ``local_irq_save/restore`` 内调用arch
dynamic init；当前IF原本为0，restore后仍为0。arch failure直接走failed。随后计算
``__start_mcount_loc..__stop_mcount_loc`` count：empty table或 ``ftrace_process_locs`` allocation/
validation failure都设置 ``ftrace_disabled=1``，而不是panic。

成功时，process-locs为built-in function sites建立 ``dyn_ftrace`` pages/groups并把initial code state
交给arch ftrace machinery；随后发布 ``last_ftrace_enabled=ftrace_enabled=1``，应用early filters。
这表示dynamic-ftrace infrastructure可用，不表示所有functions正在写trace buffer；actual tracer、
filters与boot options仍决定哪些sites被activate。

不含function tracer/dynamic ftrace的build由stubs/no-op覆盖，不能从call存在推导location table或code
patch一定发生。 ``tracefs`` 也尚未mount。

early trace先处理 ``tracepoint_printk`` 再建global buffers/events
-----------------------------------------------------------

tracing build的 ``early_trace_init`` 若parameter启用 ``tracepoint_printk``，先 ``kzalloc`` iterator；
失败就清option，成功才enable ``tracepoint_printk_key`` static key。普通 ``printk`` ring与这个trace
iterator/buffer不是同一系统。

随后 ``tracer_alloc_buffers`` 申请global trace cpumasks、ring buffers、saved-command backing并注册所需
CPUHP state，内部failure按rollback/error path留下tracing不可用或降级状态；再 ``init_events`` 准备
early event infrastructure。具体boot tracer/filter/event由054已经分发的effective parameters与build
决定，正文不假定已经采集所有函数或events。

此时放在scheduler前，是为了让后续scheduler/IRQ/timer启动尽可能可被boot tracing观察；它不依赖
已经发生调度，allocation来自055 runtime MM。完整 ``trace_init`` 仍在058之后处理trace-event/boot
instances。

本章结束状态
------------

* current executor：CPU0上的 ``start_kernel``， ``early_trace_init`` 已返回；
* precise next： ``sched_init()`` 尚未调用；
* CPU/mode：CPU0，x86-64 CPL0，IF=0， ``init_task``，无schedule/AP；
* Maple Tree： ``maple_node`` SLUB cache已建立；无用户tree/VMA；
* text poke：专用mm、chosen two-page address与page-table backing已建；没有text alias/patch驻留；
* dynamic ftrace：按build成功建立records并enable infrastructure，或failure disabled/no-op；
* ``tracepoint_printk``：按option/iterator allocation enable或关闭；
* early tracing：buffer/event early init已尝试并按actual result完成/降级；tracefs未mount；
* buddy/slab/vmalloc：保持可用；
* scheduler/runqueues/boot idle registration：尚未初始化；IRQ仍未启用。

关键边界
--------

#. Maple node cache ready不等于存在任何user mm/VMA，也不替代radix/XArray。
#. text-poke mm的预分配PTE不是RWX kernel-text mapping。
#. ``poking_init`` 准备mechanism，不执行第二轮全内核patch。
#. ftrace location records、ftrace-enabled infrastructure与actual recording是三层状态。
#. ftrace table/allocation failure禁用ftrace而非panic；Maple cache failure则因SLAB_PANIC终止。
#. build stubs必须保留，call site不证明function tracer/tracing已配置。
#. tracepoint printk与ordinary printk使用不同buffer/enable path。
#. early trace在scheduler前完成不表示已经发生task switch或timer-driven event。

下一入口
--------

第057章从：

.. code-block:: c

   sched_init();

开始，并包含return后的very-early IRQ sanity repair，停在 ``radix_tree_init`` call前。

资料
----

* `Linux 7.2-rc1固定提交：Maple/poking/ftrace/early trace顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1034-L1047>`_；
* `Linux 7.2-rc1固定提交：Maple node cache参数 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/lib/maple_tree.c#L5630-L5640>`_；
* `Linux 7.2-rc1固定提交：x86 text-poke mm/address/PTE预分配 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init.c#L815-L853>`_；
* `Linux 7.2-rc1固定提交：ftrace init success/disable paths <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/trace/ftrace.c#L8365-L8407>`_；
* `Linux 7.2-rc1固定提交：early tracepoint-printk/buffer/event顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/trace/trace.c#L9941-L9954>`_。
