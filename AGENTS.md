# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

固定主线：

```text
x86-64 → QEMU q35 → SeaBIOS → GNU GRUB 2.14 i386-pc → bzImage → Linux 7.2-rc1
```

当前已经完成 `LK-BOOT-001` 至 `LK-BOOT-070`。最新章节：

- `LK-BOOT-068`：Linux 怎样创建 PID 1、PID 2，并让 PID 0 进入 idle loop？
- `LK-BOOT-069`：Linux 怎样唤醒 AP，并让 workqueue 与 SMP scheduler 正式运行？
- `LK-BOOT-070`：Linux 怎样运行全部 built-in initcall，并准备 initramfs 与 root filesystem？

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

固定 `grub.cfg`：

```cfg
set timeout=0
set default=0

menuentry 'Linux 7.2-rc1' {
    linux /boot/bzImage-7.2-rc1 root=/dev/sda1 ro console=ttyS0
    initrd /boot/initramfs-7.2-rc1.img
}
```

GRUB 资料使用 GNU 官方 `grub-2.14.tar.xz` 和 `GitMirroring/grub` 固定提交。Linux 资料使用 `gregkh/linux` 固定 commit `7404ce51637231382873d0b55edabc2f3b841a9d`。

重要纠正：该 commit 的 `Makefile` 标识为 Linux 7.2-rc1。旧章节中残留的 `Linux 6.12.95` 只是历史显示标签错误。不得把源码切换到真正的 `v6.12.95`；技术事实以固定 commit 和链接为准。

## 当前控制流

当前已执行：

```text
start_kernel()
→ memory / allocator / scheduler / IRQ / timer / timekeeping
→ PID/fork/namespace/VFS/cgroup foundations
→ rest_init()
→ create PID 1 kernel_init
→ create PID 2 kthreadd
→ system_state = SYSTEM_SCHEDULING
→ PID 0 first schedule
→ PID 0 enters cpu_startup_entry()/idle

PID 1 kernel_init()
→ wait_for_completion(kthreadd_done)
→ kernel_init_freeable()
→ enable full GFP and memory-node access
→ smp_prepare_cpus()
→ workqueue_init()
→ pre-SMP initcalls and lockup detector
→ smp_init()
→ bring permitted APs online
→ sched_init_smp()
→ workqueue topology / async / padata / page allocator late init
→ do_basic_setup()
→ driver model and IRQ proc setup
→ pure/core/postcore/arch/subsys/fs/device/late initcalls
→ KUnit entry
→ wait_for_initramfs()
→ console_on_rootfs()
→ choose executable /init or prepare_namespace(root=/dev/sda1)
→ integrity_load_keys()
→ kernel_init_freeable() returns
```

当前主线执行者是 Linux 7.2-rc1 PID 1 `init/main.c:kernel_init()`。精确下一入口：

```c
async_synchronize_full();
```

当前状态：

- PID 0 已是 CPU0 idle task；
- PID 1 仍在 kernel mode，尚未 exec 用户态 init；
- PID 2 kthreadd 与正式 workqueue 已运行；
- 配置允许且成功启动的 AP 已 online，数量由实际 QEMU 参数和运行结果决定；
- SMP scheduler topology 已建立；
- built-in initcall 已全部调用；
- initramfs 解包等待已完成；
- root 路径已二选一：保留可执行 `/init` 的 initramfs，或 `prepare_namespace()` 尝试挂载并 pivot 到 `/dev/sda1`；
- 全局 async work 尚未最终汇合；
- `__init` memory 尚未释放；
- rodata/PTI 尚未最终收尾；
- `system_state` 尚未进入 `SYSTEM_RUNNING`。

下一任务从 `kernel_init():async_synchronize_full()` 开始，继续：

```text
async_synchronize_full()
→ system_state = SYSTEM_FREEING_INITMEM
→ kprobe/ftrace/kgdb init-memory cleanup
→ exit_boot_config()
→ free_initmem()
→ mark_readonly()
→ pti_finalize()
→ system_state = SYSTEM_RUNNING
→ numa_default_policy()
→ rcu_end_inkernel_boot()
→ do_sysctl_args()
→ try /init, init=, CONFIG_DEFAULT_INIT,
  /sbin/init, /etc/init, /bin/init, /bin/sh
→ successful kernel_execve()
→ PID 1 enters user mode
```

必须继续区分：

1. `user_mode_thread(kernel_init)` 创建 PID 1，不代表 PID 1 已进入用户态；
2. `smp_prepare_cpus()` 准备 AP，不代表 AP online；真正 bring-up 在 `smp_init()`；
3. `do_initcalls()` 返回不代表 async work/probe 全部完成；
4. initramfs 解包不代表必然已挂载 `/dev/sda1`；可执行 `/init` 会让 early userspace 接管 root 切换；
5. `kernel_execve()` 成功后 PID 1 才真正成为用户态 init。

## 用户输入与技术事实

用户提供的是关注方向、线索和阅读感受，不直接作为完整技术事实。正文根据固定硬件路径、规范、固定源码和真实状态变化补全中间过程。

## 连续叙事

每一段必须交代：

- 当前执行者；
- CPU mode 和运行环境；
- 关键代码与数据；
- 当前动作建立的条件；
- 下一控制入口；
- 对应规范、固定源码文件和符号。

不能用“固件初始化硬件”“GRUB 加载内核”“Linux 初始化内存”这样的概括跳过中间主流程。

## 章节边界

章节不按 Roadmap 条目机械切分，也不预先规划整本书。连续叙述达到适合一次阅读的篇幅，并遇到执行者、CPU mode、运行环境或控制入口交接时换章。

每章结尾记录当前执行者、状态和下一入口。章节正文不添加上一章、下一章或目录导航；章节列表统一由 `docs/tracks/linux-kernel/index.rst` 提供。

每章末尾“资料”必须使用可点击 RST 链接。技术事实优先使用规范、官方发布物和固定源码等一手资料。

## 连续推进模式

用户要求连续完成 N 章时，仍逐章执行：

1. 重新读取最新 `AGENTS.md`、`project/STATE.rst`、manifest 和当前入口；
2. 读取本章涉及的固定源码与规范；
3. 只确定当前一章的自然边界；
4. 写完并核对当前章节；
5. 更新目录、STATE、manifest、README 和接续入口；
6. 再从最新状态开始下一章。

不能先批量生成多章后统一核对。遇到固定源码无法确认、重大平台分叉、仓库写入失败或达到指定终点时停止。

## 状态语义

- `draft`：正文正在编写，或关键事实链尚未核对完整；
- `verified`：关键结论已依据固定源码或规范核对，章节仍在续写；
- `complete`：章节到达自然终点，关键事实已经核对。

读者不承担技术审稿。用户反馈只用于指出哪里难懂、希望展开或阅读不连续。

## 接手顺序

1. `AGENTS.md`；
2. `project/STATE.rst`；
3. `docs/tracks/linux-kernel/index.rst`；
4. 最新已完成章节；
5. `manifests/tracks/linux-kernel.toml`；
6. `main` 最近相关提交。

完成章节后更新正文、目录、STATE、manifest、README 和 Linux 路径状态。