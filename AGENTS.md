# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

这本书从设备上电后的故事引入，最终主题仍然是 Linux 内核。固件和 bootloader 属于内核取得控制权之前必须交代的前传，不单独扩展成硬件或固件教材。

固定主线：

``x86-64 → QEMU q35 → SeaBIOS → GNU GRUB 2.14 i386-pc → bzImage → Linux 7.2-rc1``。

当前已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-064``。最新章节是：

``LK-BOOT-064``：x86 怎样启动真实定时器、校准延时并完成 boot CPU 收尾？

## 固定实现

```text
SeaBIOS commit    = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
QEMU commit       = a759542a2c62f0fd3b65f5a66ad9868201014669
GNU GRUB release  = 2.14
GRUB commit       = d38d6a1a9b79427848976f53d474392cd29c2a71
GRUB target       = i386-pc
Linux release     = 7.2-rc1
Linux repository  = gregkh/linux
Linux commit      = 7404ce51637231382873d0b55edabc2f3b841a9d
partition table   = MBR
first partition   = LBA 2048, ext4
kernel            = /boot/bzImage-7.2-rc1
initramfs         = /boot/initramfs-7.2-rc1.img
```

固定 ``grub.cfg``：

```cfg
set timeout=0
set default=0

menuentry 'Linux 7.2-rc1' {
    linux /boot/bzImage-7.2-rc1 root=/dev/sda1 ro console=ttyS0
    initrd /boot/initramfs-7.2-rc1.img
}
```

GRUB 资料使用 GNU 官方 ``grub-2.14.tar.xz`` 和 ``GitMirroring/grub`` 固定提交。Linux 资料使用 ``gregkh/linux`` 固定 commit ``7404ce51637231382873d0b55edabc2f3b841a9d``。

重要纠正：该 commit 的 ``Makefile`` 标识为 ``Linux 7.2-rc1``。此前 ``AGENTS.md``、STATE 和 manifest 将其误写为 ``v6.12.95``。真正的 ``v6.12.95`` 是另一提交，``start_kernel()`` 顺序不同。后续不得把源码切换到 ``v6.12.95``；旧章节中残留的版本显示字符串只作为待清理标签，技术事实以固定 commit 和链接为准。

## 当前控制流

当前已经执行：

```text
start_kernel()
→ mm_core_init()
→ release memblock free RAM to buddy
→ establish slab and vmalloc
→ maple_tree_init()
→ poking_init()
→ ftrace_init()
→ early_trace_init()
→ sched_init()
→ initialize per-CPU runqueues and scheduling classes
→ bind init_task as CPU0 idle/current task
→ radix_tree_init()
→ housekeeping_init()
→ workqueue_init_early()
→ rcu_init()
→ kvfree_rcu_init()
→ trace_init()
→ context_tracking_init()
→ early_irq_init()
→ allocate IRQ descriptors and x86 VECTOR domain
→ init_IRQ()
→ install APIC/system/external gates into IDT
→ tick_init() / rcu_init_nohz()
→ timers_init() / srcu_init() / hrtimers_init() / softirq_init()
→ vdso_setup_data_pages()
→ timekeeping_init()
→ time_init()
→ random_init()
→ kfence_init()
→ boot_init_stack_canary()
→ perf_event_init() / profile_init() / call_function_init()
→ early_boot_irqs_disabled = false
→ local_irq_enable()
→ kmem_cache_init_late()
→ console_init()
→ lockdep_init() / locking_selftest()
→ setup_per_cpu_pageset()
→ numa_policy_init()
→ acpi_early_init()
→ x86_late_time_init()
→ select and initialize final interrupt mode
→ try HPET, fall back to PIT where required
→ register timer IRQ action
→ tsc_init()
→ sched_clock_init()
→ calibrate_delay()
→ arch_cpu_finalize_init()
```

当前执行者是 Linux 7.2-rc1 ``init/main.c:start_kernel()``。``arch_cpu_finalize_init()`` 已返回，精确下一入口是 ``pid_idr_init()``。

CPU0 是唯一 online CPU，当前任务是 ``init_task`` / ``swapper/0`` / PID 0。CPU0 IF=1，普通 maskable IRQ 已允许进入；最终 x86 interrupt mode、HPET/PIT fallback、TSC、sched clock 和 delay calibration 已完成对应初始化入口。boot CPU feature、idle routine、SMT、mitigation、FPU、alternative instructions 与 memory-encryption 收尾已完成。AP 尚未启动，initramfs 尚未解包，PID allocator、PID 1 和 PID 2 尚未创建。

下一任务从 ``pid_idr_init()`` 开始，依次核对 ``anon_vma_init()``、``thread_stack_cache_init()``、``cred_init()``、``fork_init()``、``proc_caches_init()``、UTS/time namespace、key/security、network namespace、VFS/page cache、signal、proc/nsfs/pidfs、cpuset、memcg 和 cgroup 基础。不要把“进程相关 cache 已建立”“PID allocator 已建立”和“PID 1 已创建”写成同一步；真正创建 PID 1/PID 2 仍在 ``rest_init()``。

## 用户输入与技术事实

用户提供的是关注方向、已知线索和阅读感受，不直接作为完整或正确的技术事实。

正文根据硬件规范、固定固件源码、启动协议、固定 GRUB/Linux 源码和真实状态变化补全中间过程。用户不知道后续流程时，Agent 继续沿当前控制流调查和写作。

## 连续叙事

正文沿一条具体路径按实际发生顺序前进。每一段交代：

* 当前是谁在执行；
* CPU 处于什么状态或模式；
* 代码和关键数据位于哪里；
* 当前动作建立了什么条件；
* 控制权下一步交给哪个入口；
* 对应哪个规范、源码文件、符号、寄存器或协议字段。

不能用“固件初始化硬件”“GRUB 加载内核”“Linux 初始化内存”这样的概括跳过中间主流程。

## 章节边界

章节不按 Roadmap 条目机械切分，也不预先规划整本书。

当连续叙述已经形成适合一次阅读的篇幅，并且附近存在执行者变化、CPU 模式变化、运行环境变化或控制入口交接时换章。每章结尾记录当前执行者、当前状态和下一入口。

章节正文不添加上一章、下一章或目录导航。章节列表统一由 ``docs/tracks/linux-kernel/index.rst`` 提供。

每章末尾的“资料”必须使用可点击的 RST 链接。技术事实优先使用规范、官方发布物和固定源码等一手资料。

## 连续推进模式

用户可要求连续完成 N 章。仍严格逐章执行：

1. 重新读取最新 ``AGENTS.md``、``project/STATE.rst``、manifest 和当前入口；
2. 读取本章涉及的固定源码与规范；
3. 只确定当前一章的自然边界；
4. 写完并核对当前章节；
5. 更新目录、状态、manifest、README 和接续入口；
6. 再从最新状态开始下一章。

连续推进不能把多章合并成一篇，也不能先批量生成后统一核对。遇到固定源码无法确认、平台路径重大分叉、仓库写入失败或达到指定终点时停止。

## 状态语义

``draft``：正文正在编写，或者关键事实链尚未核对完整。

``verified``：关键结论已依据固定源码或规范核对，章节仍在续写。

``complete``：章节到达自然终点，关键事实已经核对。

读者不承担技术审稿。用户反馈只用于指出哪里难懂、希望展开或阅读不连续。

## 接手顺序

1. ``AGENTS.md``；
2. ``project/STATE.rst``；
3. ``docs/tracks/linux-kernel/index.rst``；
4. 已完成章节；
5. ``manifests/tracks/linux-kernel.toml``；
6. ``main`` 最近的相关提交。

完成章节后更新正文、目录、``project/STATE.rst``、manifest、README 和 Linux 路径状态。