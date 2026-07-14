Linux Kernel
============

这本书讲 Linux 内核。开头从设备上电后的真实执行过程进入，先交代内核取得控制权之前发生的必要故事；启动链完成后，切换到明确的运行期入口继续追踪。

当前正文
--------

#. `第一章：按下电源键后，CPU 从哪里取得第一条指令？ <01-power-on-first-instruction.rst>`_
#. `第二章：SeaBIOS 怎样从 16 位入口进入 32 位 C 代码？ <02-seabios-entry-to-32bit-c.rst>`_
#. `第三章：SeaBIOS 怎样识别内存并把初始化代码搬到 RAM？ <03-seabios-memory-map-and-relocation.rst>`_
#. `第四章：SeaBIOS 怎样在低端内存建立 IVT、BDA 和 EBDA？ <04-seabios-ivt-bda-ebda.rst>`_
#. `第五章：SeaBIOS 怎样把自己变成可供启动软件调用的 BIOS？ <05-seabios-software-interfaces.rst>`_
#. `第六章：SeaBIOS 怎样建立中断基础并启动内部线程？ <06-seabios-dma-pic-threads.rst>`_
#. `第七章：SeaBIOS 怎样为 q35 编号 PCI 总线并发现设备？ <07-seabios-pci-bus-and-device-discovery.rst>`_
#. `第八章：SeaBIOS 怎样启用 q35 MMCONFIG 并为 PCI 设备分配地址？ <08-seabios-q35-mmconfig-and-pci-bar-allocation.rst>`_
#. `第九章：SeaBIOS 怎样接通 q35 PCI 中断并打开设备地址解码？ <09-seabios-pci-interrupt-routing-and-device-enable.rst>`_
#. `第十章：SeaBIOS 怎样进入 SMM 并把处理入口藏进 SMRAM？ <10-seabios-smm-and-smbase-relocation.rst>`_
#. `第十一章：SeaBIOS 怎样规定物理地址的缓存类型并准备每个 CPU 的 MSR？ <11-seabios-mtrr-and-feature-control.rst>`_
#. `第十二章：SeaBIOS 怎样用 INIT/SIPI 唤醒其他 CPU？ <12-seabios-smp-init-sipi-and-ap-startup.rst>`_
#. `第十三章：SeaBIOS 怎样把 CPU、IRQ 和内存信息写成固件表？ <13-seabios-pirq-mp-and-smbios-tables.rst>`_
#. `第十四章：SeaBIOS 怎样执行 QEMU 的 ACPI table-loader 并找到 RSDP？ <14-seabios-acpi-table-loader-and-rsdp.rst>`_
#. `第十五章：SeaBIOS 怎样沿 RSDP 读懂 ACPI 表图并解析 DSDT？ <15-seabios-acpi-table-graph-and-dsdt-parse.rst>`_
#. `第十六章：SeaBIOS 怎样建立时间基准、18.2 Hz BIOS 时钟并初始化 TPM？ <16-seabios-timers-clock-and-tpm.rst>`_
#. `第十七章：SeaBIOS 为什么先运行 VGA Option ROM 再初始化其他设备？ <17-seabios-vga-option-rom-and-console.rst>`_
#. `第十八章：SeaBIOS 怎样枚举 USB 设备并初始化 PS/2 键盘？ <18-seabios-usb-and-ps2-input.rst>`_
#. `第十九章：SeaBIOS 怎样发现 q35 的 AHCI 磁盘并把它加入启动列表？ <19-seabios-ahci-disk-and-bootlist.rst>`_
#. `第二十章：SeaBIOS 怎样扫描普通 Option ROM 并把 BCV、BEV 加入启动列表？ <20-seabios-option-rom-bcv-bev.rst>`_
#. `第二十一章：SeaBIOS 怎样执行 BCV 并把启动盘映射成 BIOS 0x80？ <21-seabios-bcv-drive-mapping-and-prepareboot.rst>`_
#. `第二十二章：SeaBIOS 怎样把硬盘第一扇区读到 0x7c00 并交给 GRUB？ <22-seabios-int19-mbr-handoff.rst>`_
#. `第二十三章：GRUB boot.img 怎样从 0x7c00 读出 core.img 的第一扇区？ <23-grub-boot-img-loads-diskboot.rst>`_
#. `第二十四章：GRUB diskboot.img 怎样按 blocklist 读完 core.img？ <24-grub-diskboot-blocklist-loads-core.rst>`_
#. `第二十五章：GRUB startup_raw 怎样进入保护模式并调用 grub_main？ <25-grub-startup-raw-protected-mode-and-grub-main.rst>`_
#. `第二十六章：GRUB 怎样通过 BIOS E820 建立自己的堆？ <26-grub-machine-init-e820-and-heap.rst>`_
#. `第二十七章：GRUB 怎样加载内建模块并建立 hd0、root 和 prefix？ <27-grub-built-in-modules-root-prefix-and-hd0.rst>`_
#. `第二十八章：GRUB normal 怎样找到并打开 grub.cfg？ <28-grub-normal-opens-grub-cfg.rst>`_
#. `第二十九章：GRUB 怎样解析 grub.cfg 并建立第一个 Linux 菜单项？ <29-grub-parses-config-and-builds-menuentry.rst>`_
#. `第三十章：GRUB 怎样自动选择菜单项并装入 linux 命令模块？ <30-grub-autoboots-entry-and-loads-linux-module.rst>`_
#. `第三十一章：GRUB linux 命令怎样检查并装载 Linux bzImage？ <31-grub-linux-command-loads-bzimage.rst>`_
#. `第三十二章：GRUB 怎样把 initramfs 放到内核允许的高地址？ <32-grub-initrd-placement-and-boot-parameters.rst>`_
#. `第三十三章：GRUB 怎样准备 boot_params 并把控制权交给 Linux？ <33-grub-boot-params-and-linux-handoff.rst>`_
#. `第三十四章：Linux startup_32 怎样建立 4 GiB 映射并进入 64 位模式？ <34-linux-startup32-enters-long-mode.rst>`_
#. `第三十五章：Linux startup_64 怎样把压缩内核搬到安全解压位置？ <35-linux-startup64-relocates-compressed-image.rst>`_
#. `第三十六章：Linux 怎样建立解压映射并选择正式内核的位置？ <36-linux-builds-identity-maps-and-chooses-output.rst>`_
#. `第三十七章：Linux 怎样解压 ELF 内核并进入正式 startup_64？ <37-linux-decompresses-elf-and-enters-kernel-startup64.rst>`_
#. `第三十八章：Linux common_startup_64 怎样建立 boot CPU 的最早运行上下文？ <38-linux-common-startup64-builds-boot-cpu-context.rst>`_
#. `第三十九章：x86_64_start_kernel 怎样清理临时环境并保存启动数据？ <39-linux-x86-64-start-kernel-cleans-early-environment.rst>`_
#. `第四十章：Linux 怎样进入 start_kernel 并建立最早的通用内核状态？ <40-linux-start-kernel-establishes-earliest-generic-state.rst>`_
#. `第四十一章：Linux setup_arch 怎样接管命令行并导入 E820 内存图？ <41-linux-setup-arch-imports-command-line-and-e820.rst>`_
#. `第四十二章：Linux 怎样修正 E820 并计算自己真正能管理的物理页？ <42-linux-fixes-e820-and-computes-max-pfn.rst>`_
#. `第四十三章：Linux 怎样把 E820 RAM 变成 memblock 并建立 early direct map？ <43-linux-builds-memblock-and-early-direct-map.rst>`_
#. `第四十四章：Linux 怎样扩大启动日志并确认 initramfs 与 ACPI 表可以安全访问？ <44-linux-expands-log-buffer-and-reserves-initramfs-acpi.rst>`_
#. `第四十五章：Linux 怎样从 MADT、MP table 和 SRAT 建立 CPU 拓扑与 NUMA node？ <45-linux-parses-early-acpi-and-builds-numa-nodes.rst>`_
#. `第四十六章：Linux 怎样完成 x86-64 paging 收尾并建立 KASAN shadow？ <46-linux-finalizes-paging-and-kasan-shadow.rst>`_
#. `第四十七章：Linux 怎样探测 tboot、映射 vsyscall 并在固件枚举前限制 CPU？ <47-linux-probes-tboot-maps-vsyscall-and-applies-early-limits.rst>`_
#. `第四十八章：Linux 怎样完成 ACPI、Local APIC、IOAPIC 与 possible CPU 拓扑？ <48-linux-completes-acpi-apic-and-possible-cpu-topology.rst>`_
#. `第四十九章：Linux 怎样登记物理资源并完成 setup_arch？ <49-linux-registers-resources-and-finishes-setup-arch.rst>`_
#. `第五十章：Linux 怎样把 memblock 物理内存变成 node、zone 和 struct page？ <50-linux-builds-zones-and-struct-page-map.rst>`_
#. `第五十一章：Linux 为什么再次检查 static key/static call，并怎样生成正式命令行？ <51-linux-rechecks-static-patching-and-builds-command-lines.rst>`_
#. `第五十二章：Linux 怎样确定 CPU 编号上限并把 CPU0 迁入正式 per-CPU area？ <52-linux-builds-percpu-area-and-migrates-cpu0.rst>`_
#. `第五十三章：Linux 为什么再次确认 CPU NUMA node，并把 CPU0 放入 hotplug ONLINE 状态？ <53-linux-initializes-boot-cpu-numa-and-hotplug-state.rst>`_
#. `第五十四章：Linux 怎样把 GRUB 命令行分发给内核参数和 init？ <54-linux-dispatches-kernel-command-line-and-init-arguments.rst>`_
#. `第五十五章：Linux 怎样把 memblock 空闲页交给 buddy，并建立 slab 与 vmalloc？ <55-linux-releases-memblock-to-buddy-and-starts-slab-vmalloc.rst>`_
#. `第五十六章：Linux 怎样准备 Maple Tree、文本热补丁和 ftrace？ <56-linux-prepares-maple-tree-text-poking-and-ftrace.rst>`_
#. `第五十七章：Linux 怎样建立 runqueue，并把 init_task 变成 CPU0 的 idle task？ <57-linux-initializes-runqueues-and-boot-idle-task.rst>`_
#. `第五十八章：Linux 怎样建立 early workqueue、RCU 和 trace event 基础？ <58-linux-builds-workqueue-rcu-and-trace-foundations.rst>`_
#. `第五十九章：Linux 怎样建立 IRQ descriptor 并把外部中断入口写入 IDT？ <59-linux-builds-irq-descriptors-and-x86-interrupt-gates.rst>`_
#. `第六十章：Linux 怎样建立 tick、timer wheel、hrtimer 与 softirq？ <60-linux-initializes-tick-timers-hrtimers-and-softirqs.rst>`_
#. `第六十一章：Linux 怎样建立 timekeeping，并把 x86 定时器初始化延后？ <61-linux-establishes-timekeeping-and-defers-x86-timer-init.rst>`_
#. `第六十二章：Linux 怎样完成启动期随机数并第一次打开外部中断？ <62-linux-finalizes-randomness-and-enables-external-interrupts.rst>`_
#. `第六十三章：Linux 怎样启用正式 console、锁依赖检查并完成 early ACPI？ <63-linux-enables-console-lockdep-and-early-acpi.rst>`_
#. `第六十四章：x86 怎样启动真实定时器、校准延时并完成 boot CPU 收尾？ <64-x86-starts-hardware-timers-calibrates-delay-and-finalizes-boot-cpu.rst>`_
#. `第六十五章：Linux 怎样建立 PID 分配器与 fork 对象基础？ <65-linux-builds-pid-and-fork-object-foundations.rst>`_
#. `第六十六章：Linux 怎样建立 namespace、安全框架与 VFS/proc 基础？ <66-linux-builds-namespaces-security-and-vfs-foundations.rst>`_
#. `第六十七章：Linux 怎样建立 cgroup 与 accounting，并到达 rest_init？ <67-linux-builds-cgroups-accounting-and-reaches-rest-init.rst>`_
#. `第六十八章：Linux 怎样创建 PID 1、PID 2，并让 PID 0 进入 idle loop？ <68-linux-creates-pid1-pid2-and-enters-idle.rst>`_
#. `第六十九章：Linux 怎样唤醒 AP，并让 workqueue 与 SMP scheduler 正式运行？ <69-linux-starts-aps-workqueues-and-smp-scheduler.rst>`_
#. `第七十章：Linux 怎样运行全部 built-in initcall，并准备 initramfs 与 root filesystem？ <70-linux-runs-initcalls-and-prepares-rootfs.rst>`_
#. `第七十一章：Linux 怎样释放 __init 内存并进入 SYSTEM_RUNNING？ <71-linux-frees-init-memory-and-enters-system-running.rst>`_
#. `第七十二章：Linux 怎样选择用户态 init，并把可执行映像装入 PID 1？ <72-linux-selects-init-and-loads-userspace-image.rst>`_
#. `第七十三章：x86 怎样让 PID 1 从 ret_from_fork 真正进入用户态？ <73-x86-returns-pid1-to-userspace.rst>`_
#. `第七十四章：x86-64 的 read() 怎样从用户态进入 __x64_sys_read？ <74-x86-read-syscall-enters-kernel.rst>`_
#. `第七十五章：read() 怎样从 fd 找到 ext4 文件并进入 generic_file_read_iter？ <75-read-resolves-fd-and-dispatches-through-vfs.rst>`_
#. `第七十六章：page cache miss 怎样让 ext4 构造并提交 READ bio？ <76-filemap-miss-builds-ext4-read-bio.rst>`_
#. `第七十七章：READ bio 怎样通过校验与分区重映射进入 blk-mq？ <77-read-bio-enters-generic-block-submission.rst>`_
#. `第七十八章：blk-mq 怎样把 bio 变成 SCSI READ request？ <78-blk-mq-builds-scsi-read-request.rst>`_
#. `第七十九章：SCSI READ 怎样变成 ATA taskfile并写入 AHCI command slot？ <79-scsi-read-becomes-ahci-command.rst>`_
#. `第八十章：AHCI 中断怎样确认完成的 tag，并把结果交回 SCSI？ <80-ahci-interrupt-completes-ata-and-scsi-command.rst>`_
#. `第八十一章：blk-mq completion 怎样结束 bio，并让 ext4 folio 变成 uptodate？ <81-block-completion-marks-ext4-folio-uptodate.rst>`_
#. `第八十二章：reader task 怎样复制 folio，并让 read() 返回用户态？ <82-reader-copies-folio-and-returns-from-read.rst>`_
#. `第八十三章：x86-64 的 write() 怎样进入 ext4 buffered write？ <83-x86-write-enters-ext4-buffered-path.rst>`_
#. `第八十四章：ext4 怎样把用户数据复制进 page-cache folio 并标脏？ <84-ext4-copies-user-data-into-dirty-folio.rst>`_
#. `第八十五章：O_SYNC write 怎样进入 ext4 writeback？ <85-osync-write-enters-ext4-writeback.rst>`_
#. `第八十六章：ext4 writeback 怎样把 dirty folio 变成 WRITE bio？ <86-ext4-writeback-builds-write-bio.rst>`_
#. `第八十七章：WRITE bio 怎样变成 AHCI command 并写入 PxCI？ <87-write-bio-becomes-ahci-command.rst>`_
#. `第八十八章：WRITE completion 怎样结束 folio writeback，并让 O_SYNC 等待继续？ <88-write-completion-ends-folio-writeback.rst>`_
#. `第八十九章：ext4 fsync 怎样选择 fast commit 或完整 JBD2 commit？ <89-ext4-fsync-chooses-fast-or-full-jbd2-commit.rst>`_
#. `第九十章：ext4 barrier 怎样把 journal 顺序落实到设备 cache？ <90-ext4-barrier-flushes-device-cache.rst>`_
#. `第九十一章：O_SYNC write 怎样提交 file position 并返回用户态？ <91-osync-write-returns-to-userspace.rst>`_
#. `第九十二章：x86-64 的 fork() 怎样创建一个尚不可运行的 task_struct？ <92-x86-fork-builds-inactive-task.rst>`_
#. `第九十三章：copy_process() 怎样复制资源并建立 COW 子进程？ <93-copy-process-builds-cow-child.rst>`_
#. `第九十四章：scheduler 怎样启动 child，并让 fork() 在父子进程返回不同结果？ <94-fork-parent-and-child-return.rst>`_
#. `第九十五章：child 写只读 COW 地址时，x86 #PF 怎样进入 do_wp_page？ <95-x86-cow-write-fault-enters-do-wp-page.rst>`_
#. `第九十六章：wp_page_copy() 怎样分配新 folio 并替换 child PTE？ <96-wp-page-copy-replaces-child-pte.rst>`_
#. `第九十七章：page fault 返回后，CPU 怎样重试 store 并完成 COW 隔离？ <97-page-fault-return-retries-child-store.rst>`_
#. `第九十八章：x86-64 的 execve() 怎样打开静态 ELF 并进入 load_elf_binary()？ <98-execve-opens-static-elf.rst>`_
#. `第九十九章：begin_new_exec() 怎样替换旧 mm 并建立静态 ELF 映射？ <99-begin-new-exec-replaces-mm-and-maps-elf.rst>`_
#. `第一百章：start_thread() 怎样让 execve 进入新静态 ELF 的第一条指令？ <100-exec-enters-new-static-elf-image.rst>`_
#. `第一百零一章：_exit(42) 怎样进入 do_exit() 并释放进程运行资源？ <101-child-exit-tears-down-runtime-resources.rst>`_
#. `第一百零二章：exit_notify() 怎样发送 SIGCHLD、唤醒 parent 并留下 zombie？ <102-exit-notify-wakes-parent-and-leaves-zombie.rst>`_
#. `第一百零三章：parent 的 wait4() 怎样读取 status 并最终回收 child？ <103-parent-wait4-reaps-child.rst>`_
#. `第一百零四章：openat() 怎样保留 fd 并把 /work/demo.txt 解析成 negative dentry？ <104-openat-resolves-negative-dentry.rst>`_
#. `第一百零五章：ext4_create() 怎样分配 inode 并把 demo.txt 写进目录？ <105-ext4-create-allocates-inode-and-dirent.rst>`_
#. `第一百零六章：VFS 怎样打开新 inode、发布 fd 6 并让 openat() 返回？ <106-vfs-opens-and-publishes-new-fd.rst>`_
#. `第一百零七章：首次 buffered write 怎样只预留空间而不分配物理块？ <107-first-buffered-write-creates-delalloc-state.rst>`_
#. `第一百零八章：fsync() 怎样让 writeback 分配第一个 unwritten extent 并提交数据？ <108-fsync-writeback-allocates-first-unwritten-extent.rst>`_
#. `第一百零九章：data completion 怎样转换 extent，并让 fsync() 真正返回？ <109-write-completion-converts-extent-and-fsync-returns.rst>`_
#. `第一百一十章：unlinkat() 怎样锁住父目录并进入 ext4_unlink()？ <110-unlinkat-locks-parent-and-enters-ext4-unlink.rst>`_
#. `第一百一十一章：ext4_unlink() 怎样删除名称，却让 fd 6 继续访问 inode？ <111-ext4-unlink-removes-name-and-keeps-open-inode.rst>`_
#. `第一百一十二章：close(6) 怎样触发最后一次 __fput() 并回收 ext4 inode？ <112-close-evicts-unlinked-ext4-inode.rst>`_
#. `第一百一十三章：clock_nanosleep() 怎样建立 hrtimer 并让 parent 阻塞？ <113-clock-nanosleep-arms-hrtimer-and-blocks-parent.rst>`_
#. `第一百一十四章：local APIC timer interrupt 怎样运行 hrtimer callback 并唤醒 parent？ <114-lapic-timer-interrupt-wakes-sleeping-parent.rst>`_
#. `第一百一十五章：scheduler 怎样恢复 parent，并让 clock_nanosleep() 返回 0？ <115-scheduler-resumes-parent-and-nanosleep-returns.rst>`_
#. `第一百一十六章：tgkill() 怎样排入 SIGUSR1 并唤醒 nanosleep 中的 parent？ <116-tgkill-wakes-interruptible-nanosleep.rst>`_
#. `第一百一十七章：parent 怎样取消 hrtimer、写回 remaining 并进入 SIGUSR1 handler？ <117-nanosleep-cancels-timer-and-builds-signal-frame.rst>`_
#. `第一百一十八章：rt_sigreturn() 怎样恢复被 SIGUSR1 中断的 clock_nanosleep 上下文？ <118-rt-sigreturn-restores-interrupted-nanosleep.rst>`_
#. `第一百一十九章：pipe2() 怎样建立匿名管道并发布 fd 6/7？ <119-pipe2-builds-anonymous-pipe-and-publishes-fds.rst>`_
#. `第一百二十章：空管道 read() 怎样进入 exclusive wait queue 并阻塞？ <120-empty-pipe-read-enters-exclusive-wait.rst>`_
#. `第一百二十一章：pipe write() 怎样唤醒reader并让 read() 返回5？ <121-pipe-write-wakes-reader-and-read-returns.rst>`_
#. `第一百二十二章：close(7) 怎样撤销 write end 并把 writers 降为 0？ <122-close-write-end-drops-pipe-writers.rst>`_
#. `第一百二十三章：空管道在 writers=0 时，read() 为什么直接返回 EOF？ <123-empty-pipe-without-writers-returns-eof.rst>`_
#. `第一百二十四章：最后一次 close(6) 怎样释放pipe page、ring与pseudo inode？ <124-final-read-end-close-frees-pipe.rst>`_
#. `第一百二十五章：FUTEX_WAIT_PRIVATE 怎样建立private key并把parent排入hash bucket？ <125-futex-wait-private-enqueues-parent.rst>`_
#. `第一百二十六章：FUTEX_WAKE_PRIVATE 怎样移除waiter并把parent放回runqueue？ <126-futex-wake-private-dequeues-and-wakes-parent.rst>`_
#. `第一百二十七章：parent 被唤醒后，futex_wait 为什么返回0却不自动重读用户字？ <127-futex-wait-returns-without-rechecking-user-word.rst>`_
#. `第一百二十八章：eventfd2() 怎样建立counter并发布fd 6？ <128-eventfd2-creates-counter-and-publishes-fd.rst>`_
#. `第一百二十九章：eventfd read() 怎样在counter为0时进入locked wait queue？ <129-empty-eventfd-read-enters-locked-wait-queue.rst>`_
#. `第一百三十章：eventfd write() 怎样唤醒reader并让read()返回counter？ <130-eventfd-write-wakes-reader-and-read-returns-counter.rst>`_
#. `第一百三十一章：close(6) 怎样撤销eventfd fd并同步进入最后一次__fput()？ <131-close-eventfd-fd-enters-final-fput.rst>`_
#. `第一百三十二章：eventfd_release() 怎样发送EPOLLHUP并释放eventfd_ctx？ <132-eventfd-release-sends-hup-and-frees-ctx.rst>`_
#. `第一百三十三章：__fput() 怎样释放anon-inode path并让close()返回0？ <133-final-eventfd-file-teardown-returns-close.rst>`_
#. `第一百三十四章：epoll_ctl(ADD) 怎样把eventfd callback挂进wait queue？ <134-epoll-add-attaches-eventfd-callback.rst>`_
#. `第一百三十五章：epoll_wait() 怎样把parent挂到eventpoll自己的wait queue？ <135-epoll-wait-blocks-on-eventpoll-wq.rst>`_
#. `第一百三十六章：eventfd write怎样触发epoll callback并让epoll_wait返回1？ <136-eventfd-write-wakes-epoll-and-delivers-level-event.rst>`_

当前主线
--------

::

   x86-64 → QEMU q35 → SeaBIOS → GNU GRUB 2.14 i386-pc
   → bzImage → Linux 7.2-rc1
   → boot handoff complete
   → cold-miss read and O_SYNC write complete
   → fork / COW / static exec / exit-wait complete
   → ext4 create-write-fsync-unlink-close lifecycle complete
   → natural and SIGUSR1-interrupted monotonic nanosleep complete
   → anonymous pipe lifecycle complete
   → private futex wait/wake complete
   → eventfd read/wake and final close complete
   → new eventfd fd 6 and eventpoll fd 7 created
   → epoll_ctl ADD installs callback P on E.wqh
   → epitem I enters EP.rbr while EP.rdllist remains empty
   → parent blocks exclusively on EP.wq in epoll_wait
   → helper writes u64 5 and E.count becomes 5
   → ep_poll_callback links I to EP.rdllist and wakes parent
   → parent re-polls eventfd and receives EPOLLIN with data 0xEFD6
   → epoll_wait returns 1
   → level-triggered I remains ready because counter is still 5

固定 commit 的 ``Makefile`` 标识为 Linux 7.2-rc1。旧章节中出现的 ``Linux 6.12.95`` 是历史版本标签错误；技术事实与链接一直以固定 commit 为准。

当前十七个运行期源码实验均已闭环：cold-miss ``read()``、O_SYNC buffered ``write()``、native ``fork()``、child COW write fault、static ``execve()``、child exit + parent wait/reap、ext4 ``openat(O_CREAT|O_EXCL)``、新文件首次delalloc write + fsync、open-unlinked文件的final close/eviction、自然到期monotonic nanosleep、``SIGUSR1`` 中断nanosleep与 ``rt_sigreturn``、anonymous pipe读写与final teardown、private futex wait/wake、eventfd counter blocking read/writer wakeup、eventfd final close，以及eventfd level-triggered epoll callback/wait delivery。下一条runtime主线尚未选择。

章节组织
--------

正文沿时间线连续讲述。故事达到适合一次阅读的篇幅，并遇到执行者、CPU mode、运行环境或控制入口交接时换章。每章末尾记录当前执行者、当前状态和下一入口。

章节完成状态由固定源码和规范核对决定。读者反馈用于指出哪里难懂、希望展开或阅读不连续，不承担技术审稿。
