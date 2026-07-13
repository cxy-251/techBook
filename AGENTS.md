# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

这本书从设备上电后的故事引入，最终主题仍然是 Linux 内核。固件和 bootloader 属于内核取得控制权之前必须交代的前传，不单独扩展成硬件或固件教材。

固定主线：

``x86-64 → QEMU q35 → SeaBIOS → GNU GRUB 2.14 i386-pc → bzImage → Linux 6.12.95``。

当前已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-049``。最新章节是：

``LK-BOOT-049``：Linux 怎样登记物理资源并完成 setup_arch？

## 固定实现

```text
SeaBIOS commit    = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
QEMU commit       = a759542a2c62f0fd3b65f5a66ad9868201014669
GNU GRUB release  = 2.14
GRUB commit       = d38d6a1a9b79427848976f53d474392cd29c2a71
GRUB target       = i386-pc
Linux release     = 6.12.95
Linux source tag  = gregkh/linux v6.12.95
Linux commit      = 7404ce51637231382873d0b55edabc2f3b841a9d
partition table   = MBR
first partition   = LBA 2048, ext4
kernel            = /boot/bzImage-6.12.95
initramfs         = /boot/initramfs-6.12.95.img
```

固定 ``grub.cfg``：

```cfg
set timeout=0
set default=0

menuentry 'Linux 6.12.95' {
    linux /boot/bzImage-6.12.95 root=/dev/sda1 ro console=ttyS0
    initrd /boot/initramfs-6.12.95.img
}
```

GRUB 资料使用 GNU 官方 ``grub-2.14.tar.xz`` 和 ``GitMirroring/grub`` 固定提交。Linux 资料使用 ``gregkh/linux`` 的 ``v6.12.95`` tag 和对应 commit。

## 当前控制流

当前已经执行：

```text
setup_arch()
→ early ACPI / NUMA / paging preparation
→ tboot / vsyscall / early quirks
→ full ACPI / Local APIC / IOAPIC / possible CPU topology
→ e820__reserve_resources()
→ e820__register_nosave_regions(max_pfn)
→ reserve_standard_io_resources()
→ e820__setup_pci_gap()
→ conditional VGA registration
→ wallclock backend selection
→ therm_lvt_init()
→ mcheck_init()
→ register_refined_jiffies(CLOCK_TICK_RATE)
→ unwind_init()
→ return from setup_arch()
```

当前执行者已经回到 Linux 6.12.95 ``init/main.c:start_kernel()``。``setup_arch(&command_line)`` 已返回，精确下一入口是 ``mm_core_init_early()``。CPU 0 正在 ``init_task`` 上执行，中断关闭，``early_boot_irqs_disabled`` 为 true。resource tree、ACPI/APIC/IOAPIC/NUMA/possible CPU 拓扑已建立；buddy allocator、per-CPU area、scheduler、AP 启动和 initramfs 解包均尚未发生。

下一任务从 ``start_kernel():mm_core_init_early()`` 开始，沿真实源码顺序处理通用内存管理早期核心、``jump_label_init()``、``static_call_init()``、``early_security_init()``、``setup_boot_config()``、``setup_command_line()``、``setup_nr_cpu_ids()`` 和 ``setup_per_cpu_areas()``。不要直接跳到 ``sched_init()``、``smp_init()``、``populate_rootfs()`` 或 ``kernel_init()``。

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