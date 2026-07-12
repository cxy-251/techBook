# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

这本书从设备上电后的故事引入，最终主题仍然是 Linux 内核。固件和 bootloader 属于内核取得控制权之前必须交代的前传，不单独扩展成硬件或固件教材。

固定主线：

``x86-64 → QEMU q35 → SeaBIOS → GNU GRUB 2.14 i386-pc → bzImage → Linux 6.12.95``。

当前已经完成：

#. ``LK-BOOT-001``：按下电源键后，CPU 从哪里取得第一条指令？
#. ``LK-BOOT-002``：SeaBIOS 怎样从 16 位入口进入 32 位 C 代码？
#. ``LK-BOOT-003``：SeaBIOS 怎样识别内存并把初始化代码搬到 RAM？
#. ``LK-BOOT-004``：SeaBIOS 怎样在低端内存建立 IVT、BDA 和 EBDA？
#. ``LK-BOOT-005``：SeaBIOS 怎样把自己变成可供启动软件调用的 BIOS？
#. ``LK-BOOT-006``：SeaBIOS 怎样建立中断基础并启动内部线程？
#. ``LK-BOOT-007``：SeaBIOS 怎样为 q35 编号 PCI 总线并发现设备？
#. ``LK-BOOT-008``：SeaBIOS 怎样启用 q35 MMCONFIG 并为 PCI 设备分配地址？
#. ``LK-BOOT-009``：SeaBIOS 怎样接通 q35 PCI 中断并打开设备地址解码？
#. ``LK-BOOT-010``：SeaBIOS 怎样进入 SMM 并把处理入口藏进 SMRAM？
#. ``LK-BOOT-011``：SeaBIOS 怎样规定物理地址的缓存类型并准备每个 CPU 的 MSR？
#. ``LK-BOOT-012``：SeaBIOS 怎样用 INIT/SIPI 唤醒其他 CPU？
#. ``LK-BOOT-013``：SeaBIOS 怎样把 CPU、IRQ 和内存信息写成固件表？
#. ``LK-BOOT-014``：SeaBIOS 怎样执行 QEMU 的 ACPI table-loader 并找到 RSDP？
#. ``LK-BOOT-015``：SeaBIOS 怎样沿 RSDP 读懂 ACPI 表图并解析 DSDT？
#. ``LK-BOOT-016``：SeaBIOS 怎样建立时间基准、18.2 Hz BIOS 时钟并初始化 TPM？
#. ``LK-BOOT-017``：SeaBIOS 为什么先运行 VGA Option ROM 再初始化其他设备？
#. ``LK-BOOT-018``：SeaBIOS 怎样枚举 USB 设备并初始化 PS/2 键盘？
#. ``LK-BOOT-019``：SeaBIOS 怎样发现 q35 的 AHCI 磁盘并把它加入启动列表？
#. ``LK-BOOT-020``：SeaBIOS 怎样扫描普通 Option ROM 并把 BCV、BEV 加入启动列表？
#. ``LK-BOOT-021``：SeaBIOS 怎样执行 BCV 并把启动盘映射成 BIOS 0x80？
#. ``LK-BOOT-022``：SeaBIOS 怎样把硬盘第一扇区读到 0x7c00 并交给 GRUB？
#. ``LK-BOOT-023``：GRUB boot.img 怎样从 0x7c00 读出 core.img 的第一扇区？
#. ``LK-BOOT-024``：GRUB diskboot.img 怎样按 blocklist 读完 core.img？
#. ``LK-BOOT-025``：GRUB startup_raw 怎样进入保护模式并调用 grub_main？
#. ``LK-BOOT-026``：GRUB 怎样通过 BIOS E820 建立自己的堆？

## 当前固定 GRUB 路径

```
GNU GRUB release = 2.14
release commit   = d38d6a1a9b79427848976f53d474392cd29c2a71
target           = i386-pc
partition table  = MBR
first partition  = LBA 2048
first filesystem = ext4
GRUB directory   = /boot/grub
boot.img         = LBA 0
core.img         = contiguous from LBA 1
```

权威发布物是 GNU 官方 ``grub-2.14.tar.xz``。源码引用使用 ``GitMirroring/grub`` 的固定发布提交。

## 当前控制流

SeaBIOS 固件阶段以及 GRUB ``boot.img → diskboot.img → startup_raw`` 阶段已经完成。

GRUB 当前已经执行：

```
grub_main()
→ grub_machine_init()
→ conditional VIA cache workaround
→ grub_modbase points into preload area above 0x100000
→ grub_console_init()
→ INT 15h E820 through protected/real-mode bridge
→ filter available RAM above 1 MiB and below 4 GiB
→ exclude preloaded module area
→ grub_mm_init_region() for each usable region
→ grub_tsc_init()
→ grub_machine_init() returns
```

当前执行者仍是 GNU GRUB 2.14 ``grub_main()``。CPU 处于 32 位保护模式，分页关闭；早期 console、E820 heap 和 TSC 时间源已经建立。core.img 内建 ELF 模块、``root/prefix``、``hd0``、``grub.cfg``、GRUB 菜单和 Linux ``bzImage`` 尚未处理。

下一任务从 ``grub_machine_init()`` 返回后开始，追踪 verifier、core.img 预装对象、``grub_load_modules()``、模块构造函数、``biosdisk``、``part_msdos``、ext4 所用 ``ext2`` 模块，以及 embedded prefix ``(,msdos1)/boot/grub`` 怎样与启动盘 ``hd0`` 合并为最终 ``root`` 和 ``prefix``。

## 用户输入与技术事实

用户提供的是关注方向、已知线索和阅读感受，不直接作为完整或正确的技术事实。

正文根据硬件规范、固定固件源码、启动协议、固定 GRUB/Linux 源码和真实状态变化补全中间过程。用户不知道后续流程时，Agent 继续沿当前控制流调查和写作。

``aiBook`` 的 Linux Kernel Roadmap 只用于确认希望掌握的知识范围。旧 Roadmap 的章节顺序和篇幅不作为新书结构。

## 连续叙事

正文沿一条具体路径按实际发生顺序前进。每一段交代：

* 当前是谁在执行；
* CPU 处于什么状态或模式；
* 代码和关键数据位于哪里；
* 当前动作建立了什么条件；
* 控制权下一步交给哪个入口；
* 对应哪个规范、源码文件、符号、寄存器或协议字段。

不能用“固件初始化硬件”“GRUB 加载内核”这样的概括跳过中间主流程。概念在流程第一次需要时直接解释。

## 章节边界

章节不按 Roadmap 条目机械切分，也不预先规划整本书。

当连续叙述已经形成适合一次阅读的篇幅，并且附近存在执行者变化、CPU 模式变化、运行环境变化或控制入口交接时换章。每章结尾记录当前执行者、当前状态和下一入口。

章节正文不添加上一章、下一章或目录导航。章节列表统一由 ``docs/tracks/linux-kernel/index.rst`` 提供。

每章末尾的“资料”必须使用可点击的 RST 链接，不能只写文件名或文档名。技术事实优先使用规范、官方发布物和固定源码等一手资料。

## 连续推进模式

用户可以用一次指令要求“连续完成 N 章”或“连续推进到某个真实控制流节点”。此时不等待逐章确认，仍然严格按下面的循环逐章执行：

#. 重新读取最新 ``AGENTS.md``、``project/STATE.rst``、manifest 和当前入口；
#. 读取本章涉及的固定源码与规范；
#. 只确定当前一章的自然边界；
#. 写完并核对当前章节；
#. 更新目录、状态、manifest、README 和接续入口；
#. 再从刚写入的最新状态开始下一章。

连续推进不能把多章合并成一篇，也不能先批量生成后统一核对。遇到固定源码无法确认、平台路径发生重大分叉、仓库写入失败或已达到用户指定终点时停止；已经完成的章节和断点必须保持可接续。

## 状态语义

``draft``
   正文正在编写，或者关键事实链尚未核对完成。

``verified``
   关键结论已经依据固定源码或规范核对，章节仍在续写。

``complete``
   章节到达自然终点，关键事实已经核对。

读者不承担技术审稿。用户反馈只用于指出哪里难懂、希望展开或阅读不连续。

## 当前内容依据

* x86-64 处理器复位状态、保护模式、SMM、MTRR、MSR、APIC 与 INIT/SIPI 资料；
* PIRQ、Intel MP Specification、SMBIOS、ACPI、PIT、RTC、TPM、PCI Option ROM、PnP BIOS、VGA BIOS、USB、HID boot protocol、i8042、AHCI、ATA/ATAPI、BIOS drive mapping、FDPT、PMM、``INT 19h``、``INT 13h`` 与 MBR 资料；
* SeaBIOS 固定源码提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* QEMU 固定参考提交 ``a759542a2c62f0fd3b65f5a66ad9868201014669``；
* GNU GRUB 2.14 官方发布物和发布提交 ``d38d6a1a9b79427848976f53d474392cd29c2a71``；
* GRUB ``boot.S``、``diskboot.S``、``startup_raw.S``、``realmode.S``、``startup.S``、``main.c``、``init.c``、``mmap.c``、``mm.c``、``tsc.c``、``util/setup.c``、``util/mkimage.c``、``util/grub-install.c``；
* Linux 6.12.95 固定源码；
* Linux/x86 Boot Protocol；
* 能从源码、寄存器、CPU 模式和内存布局确认的状态变化。

## 接手顺序

开始工作前依次读取：

#. ``AGENTS.md``；
#. ``project/STATE.rst``；
#. ``docs/tracks/linux-kernel/index.rst``；
#. 已完成章节；
#. ``manifests/tracks/linux-kernel.toml``；
#. ``main`` 最近的相关提交。

## 工作结束

完成章节后更新正文、目录、``project/STATE.rst``、manifest、README 和 Linux 路径状态。
