# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

已经完成：

```text
LK-BOOT-001..LK-BOOT-073
LK-READ-074..LK-READ-082
LK-WRITE-083..LK-WRITE-091
LK-FORK-092..LK-FORK-094
LK-COW-095..LK-COW-097
```

四个运行期实验已闭环：

- cold-miss `read(fd, buf, 4096)`；
- ext4 `O_SYNC write(fd, buf, 4096)`；
- native x86-64 `fork()`；
- child private-anonymous COW write fault。

最新三章：

- `LK-COW-095`：child 写只读 COW 地址时，x86 #PF 怎样进入 do_wp_page？
- `LK-COW-096`：wp_page_copy() 怎样分配新 folio 并替换 child PTE？
- `LK-COW-097`：page fault 返回后，CPU 怎样重试 store 并完成 COW 隔离？

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
storage           = q35 ICH9 AHCI SATA port 0
```

固定 commit 的 `Makefile` 标识为 Linux 7.2-rc1。旧章节中的 `Linux 6.12.95` 是历史显示标签错误。

## 已完成 COW 固定场景

```text
current task       = fork child
userspace action   = store one 32-bit value to address A
VMA                = private anonymous, VM_READ | VM_WRITE
child PTE          = present, user, read-only
parent PTE         = present, user, read-only
old folio          = normal 4 KiB anonymous folio
sharing            = parent and child both map old folio
fault code         = X86_PF_PROT | X86_PF_WRITE | X86_PF_USER
reuse              = impossible; actual wp_page_copy required
excluded           = THP, KSM, userfaultfd, swap, migration, zero page,
                     device-private page, GUP pin, pkey, shadow stack
failure policy     = no allocation, memcg, copy, signal or OOM failure
```

## 已执行 COW 控制流

```text
child userspace store
→ x86 vector 14 #PF
→ asm_exc_page_fault / exc_page_fault
→ CR2 fault address
→ do_user_addr_fault
→ FAULT_FLAG_WRITE | FAULT_FLAG_USER
→ per-VMA lock or mmap_read_lock fallback
→ handle_mm_fault
→ __handle_mm_fault
→ handle_pte_fault
→ do_wp_page
→ reject PageAnonExclusive/wp_can_reuse_anon_folio
→ folio_get(old)
→ release child PTL
→ wp_page_copy
→ allocate and memcg-charge new small anonymous folio
→ copy PAGE_SIZE old contents
→ mark new folio uptodate
→ MMU notifier invalidate start
→ reacquire PTL and revalidate orig_pte
→ ptep_clear_flush child old translation
→ add exclusive anonymous rmap and LRU state
→ install writable/young/dirty child PTE
→ remove child rmap from old folio
→ MMU notifier invalidate end
→ child min_flt increment
→ irqentry_exit / IRETQ
→ CPU retries original store
→ store succeeds on child new folio
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
runtime scenario   = COW write fault complete
current executor   = child
CPU mode           = x86-64 CPL 3
current location   = instruction after completed store
child virtual A    = new anonymous folio
child PTE          = present, user, writable, young, dirty
child folio        = uptodate, exclusive, contains modified value
parent virtual A   = old anonymous folio
parent PTE         = present, user, read-only
parent folio       = retains original value
child min_flt      = incremented by one
child maj_flt      = unchanged
next entry         = unselected runtime scenario
```

## 下一建议场景

优先候选是 child执行 native `execve()`，继续进程生命周期主线。

开始前必须固定：

```text
current task       = child after completed COW store
userspace call     = native execve(path, argv, envp)
executable path    = exact path on ext4
ELF form           = static or dynamically linked; must choose one
interpreter        = exact PT_INTERP path when dynamic
argv/envp          = fixed small arrays
credentials        = no setuid/setgid/file capabilities unless explicitly selected
ptrace/seccomp     = disabled
files              = define any FD_CLOEXEC descriptors
cache state        = define pathname/dentry/inode/page-cache state
failure policy     = no lookup, permission, allocation, ELF, interpreter or LSM failure
```

预计核对：

```text
entry_SYSCALL_64 / __x64_sys_execve
→ do_execveat_common
→ filename/path lookup
→ bprm_execve
→ prepare_binprm
→ search_binary_handler
→ load_elf_binary
→ begin_new_exec
→ new mm / ELF PT_LOAD mappings
→ interpreter loading if selected
→ argv/envp/auxv user stack
→ close-on-exec and signal reset
→ old mm release
→ start_thread
→ return to new userspace entry point
```

不要默认动态 ELF 或静态 ELF；两者路径差异很大。不要把 exec描述成创建新进程：PID/task通常保留，当前 image和 mm被替换。

## 必须保持的技术边界

1. 不同运行期实验之间不是自动连续时间线。
2. VMA writable与 PTE writable是不同权限层次。
3. fork后的 write fault存在 exclusive reuse优化；只有固定共享状态后才能写死 copy。
4. 新 folio分配、PAGE_SIZE copy、PTE替换、TLB flush和用户 store重试必须分开。
5. `wp_page_copy()` 返回时原用户 store尚未执行。
6. page fault通过 IRETQ返回 faulting RIP，不使用 SYSRETQ。
7. child COW只修改 child页表；parent PTE不自动恢复 writable。
8. minor fault可以包含物理页分配与 4 KiB copy。
9. exec创建新 image，不创建新 PID/task。
10. static/dynamic ELF、interpreter与page-cache状态必须在 exec场景开始前固定。

## 连续叙事

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。不能用“触发 COW”“加载 ELF”“替换进程”跳过实际对象转换。

## 章节边界

遇到执行者、CPU mode、数据结构所有权、运行环境或 subsystem交接时换章。章节正文不添加上一章、下一章或目录导航；资料使用可点击 RST链接。

## 连续推进模式

1. 读取最新 `AGENTS.md`、`project/STATE.rst`、manifest和当前入口；
2. 固定新的运行期场景；
3. 读取 fixed source；
4. 确定自然边界；
5. 写完并核对章节；
6. 更新目录、STATE、manifest、README和接续入口。

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
6. `main` 最近相关提交。
