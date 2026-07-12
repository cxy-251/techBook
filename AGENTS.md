# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

这本书从设备上电后的故事引入，最终主题仍然是 Linux 内核。固件和 bootloader 属于内核取得控制权之前必须交代的前传，不单独扩展成硬件或固件教材。

固定主线：

``x86-64 → QEMU q35 → SeaBIOS → GNU GRUB 2.14 i386-pc → bzImage → Linux 6.12.95``。

当前已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-032``。最新章节是：

``LK-BOOT-032``：GRUB 怎样把 initramfs 放到内核允许的高地址？

## 当前固定路径

```text
GNU GRUB release = 2.14
release commit   = d38d6a1a9b79427848976f53d474392cd29c2a71
target           = i386-pc
partition table  = MBR
first partition  = LBA 2048
first filesystem = ext4
GRUB directory   = /boot/grub
boot.img         = LBA 0
core.img         = contiguous from LBA 1
built-in modules = biosdisk part_msdos ext2 normal + dependencies
embedded prefix  = (,msdos1)/boot/grub
Linux release    = 6.12.95
Linux source     = gregkh/linux tag v6.12.95
```

固定 ``/boot/grub/grub.cfg``：

```cfg
set timeout=0
set default=0

menuentry 'Linux 6.12.95' {
    linux /boot/bzImage-6.12.95 root=/dev/sda1 ro console=ttyS0
    initrd /boot/initramfs-6.12.95.img
}
```

权威 GRUB 发布物是 GNU 官方 ``grub-2.14.tar.xz``。源码引用使用 ``GitMirroring/grub`` 的固定发布提交。Linux 源码固定为 ``gregkh/linux`` 的 ``v6.12.95`` tag。

## 当前控制流

SeaBIOS、GRUB 磁盘阶段、``grub_main()``、配置解析、菜单选择、``linux.mod`` 动态装载、``bzImage`` 与 initramfs 读取已经完成。

当前已经执行：

```text
grub_cmd_initrd()
→ open /boot/initramfs-6.12.95.img with NO_DECOMPRESS
→ calculate true size and 4 KiB aligned size
→ addr_max = min(initrd_addr_max, 0x37ffffff, optional mem=) - 0x10000
→ addr_min = prot_mode_target + prot_init_space
→ allocate high-preference relocator chunk
→ copy original initramfs bytes
→ ramdisk_image = initrd_mem_target
→ ramdisk_size = true file size
→ finish entry sourcecode
→ stop immediately before implicit boot
```

当前执行者是 GNU GRUB 2.14 菜单项执行路径。CPU 处于 32 位保护模式，分页关闭。Linux protected-mode payload 与 initramfs 都已装入 relocator 管理的内存；loader hook 是 ``grub_linux_boot``；Linux 尚未取得控制权。

下一任务从 ``grub_menu_execute_entry()`` 的隐式 ``grub_command_execute("boot")`` 开始，进入 ``grub_linux_boot()``，完成 video、低端 boot_params、命令行、E820 和 relocator 状态，随后以 ``ESI=boot_params``、``EIP=code32_start`` 把控制权交给 Linux compressed ``startup_32``。

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

不能用“固件初始化硬件”“GRUB 加载内核”这样的概括跳过中间主流程。概念在流程第一次需要时直接解释。

## 章节边界

章节不按 Roadmap 条目机械切分，也不预先规划整本书。

当连续叙述已经形成适合一次阅读的篇幅，并且附近存在执行者变化、CPU 模式变化、运行环境变化或控制入口交接时换章。每章结尾记录当前执行者、当前状态和下一入口。

章节正文不添加上一章、下一章或目录导航。章节列表统一由 ``docs/tracks/linux-kernel/index.rst`` 提供。

每章末尾的“资料”必须使用可点击的 RST 链接。技术事实优先使用规范、官方发布物和固定源码等一手资料。

## 连续推进模式

用户可以用一次指令要求“连续完成 N 章”或“连续推进到某个真实控制流节点”。此时仍严格逐章执行：

1. 重新读取最新 ``AGENTS.md``、``project/STATE.rst``、manifest 和当前入口；
2. 读取本章涉及的固定源码与规范；
3. 只确定当前一章的自然边界；
4. 写完并核对当前章节；
5. 更新目录、状态、manifest、README 和接续入口；
6. 再从刚写入的最新状态开始下一章。

连续推进不能把多章合并成一篇，也不能先批量生成后统一核对。遇到固定源码无法确认、平台路径发生重大分叉、仓库写入失败或达到指定终点时停止。

## 状态语义

``draft``：正文正在编写，或者关键事实链尚未核对完成。

``verified``：关键结论已经依据固定源码或规范核对，章节仍在续写。

``complete``：章节到达自然终点，关键事实已经核对。

读者不承担技术审稿。用户反馈只用于指出哪里难懂、希望展开或阅读不连续。

## 接手顺序

开始工作前依次读取：

1. ``AGENTS.md``；
2. ``project/STATE.rst``；
3. ``docs/tracks/linux-kernel/index.rst``；
4. 已完成章节；
5. ``manifests/tracks/linux-kernel.toml``；
6. ``main`` 最近的相关提交。

完成章节后更新正文、目录、``project/STATE.rst``、manifest、README 和 Linux 路径状态。
