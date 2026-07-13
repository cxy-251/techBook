# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

固定主线：

```text
x86-64 → QEMU q35 → SeaBIOS → GNU GRUB 2.14 i386-pc → bzImage → Linux 7.2-rc1
```

当前已经完成 `LK-BOOT-001` 至 `LK-BOOT-073`。最新章节：

- `LK-BOOT-071`：Linux 怎样释放 __init 内存并进入 SYSTEM_RUNNING？
- `LK-BOOT-072`：Linux 怎样选择用户态 init，并把可执行映像装入 PID 1？
- `LK-BOOT-073`：x86 怎样让 PID 1 从 ret_from_fork 真正进入用户态？

Linux boot 主线已经到达自然终点：PID 1 已通过 exec 和 x86 exit-to-user 路径进入第一条用户指令。

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

重要纠正：该 commit 的 `Makefile` 标识为 Linux 7.2-rc1。旧章节中残留的 `Linux 6.12.95` 只是历史显示标签错误。不得切换到真正的 `v6.12.95`；技术事实以固定 commit 和链接为准。

## 当前控制流

已经执行：

```text
start_kernel()
→ memory / scheduler / IRQ / timer / VFS / cgroup foundations
→ rest_init()
→ create PID 1 and PID 2
→ PID 0 enters idle

PID 1 kernel_init_freeable()
→ bring APs online
→ initialize workqueue/SMP scheduler/driver model
→ run all built-in initcalls
→ process initramfs and root branch

PID 1 kernel_init()
→ async_synchronize_full()
→ SYSTEM_FREEING_INITMEM
→ free_initmem()
→ mark_readonly()
→ pti_finalize()
→ SYSTEM_RUNNING
→ rcu_end_inkernel_boot()
→ do_sysctl_args()
→ choose init candidate
→ kernel_execve()
→ binary-format handler / ELF loading
→ START_THREAD()
→ return into ret_from_fork()
→ syscall_exit_to_user_mode()
→ x86 PTI/FRED/iretq exit
→ PID 1 enters userspace
```

当前状态：

- `system_state = SYSTEM_RUNNING`；
- PID 0 与 AP idle tasks 正常运行；
- PID 1 已进入用户态 init、dynamic linker 或 script interpreter；
- PID 2 `kthreadd` 正常运行；
- `__init` memory 已释放；
- kernel text/rodata 已最终只读化；
- 成功 exec 的 user mm、stack、argv/envp/auxv 已激活；
- 启用 PTI 时 PID 1 正使用 user CR3；
- Linux boot handoff 已完成。

## 下一任务边界

固定主线没有锁定 initramfs 内容、最终 init binary 和用户态执行日志，不能猜测 PID 1 的第一条 syscall。

继续时必须先选择一个明确运行期场景，并固定入口，例如：

```text
read()
openat()
fork()/clone()
page fault
timer interrupt
block I/O through AHCI
```

选定后，从真实用户态 syscall、IDT exception 或 hardware interrupt 入口重新建立连续调用链。不要把多个运行期场景混成一条“系统接下来自动发生”的时间线。

## 必须保持的技术边界

1. `SYSTEM_RUNNING` 不等于 PID 1 已进入用户态；真正交接发生在 `iretq`/FRED。
2. `START_THREAD()` 只准备 `pt_regs`，不切换 CPL。
3. `kernel_execve()` 成功不创建新 PID；仍是同一个 PID 1。
4. dynamic ELF 第一条用户指令通常在 dynamic linker，不是 C `main`。
5. `do_initcalls()` 返回不代表 async work 已完成；全局屏障是 `async_synchronize_full()`。
6. initramfs 解包不等于必然挂载 `/dev/sda1`；可执行 `/init` 会接管 root 切换。
7. driver model 建立不等于所有硬件 driver 均成功 probe。

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

## 接手顺序

1. `AGENTS.md`；
2. `project/STATE.rst`；
3. `docs/tracks/linux-kernel/index.rst`；
4. 已完成章节；
5. `manifests/tracks/linux-kernel.toml`；
6. `main` 最近的相关提交。
