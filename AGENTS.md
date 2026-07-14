# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

```text
LK-BOOT-001..LK-BOOT-073
LK-READ-074..LK-READ-082
LK-WRITE-083..LK-WRITE-091
LK-FORK-092..LK-FORK-094
LK-COW-095..LK-COW-097
LK-EXEC-098..LK-EXEC-100
LK-EXIT-101..LK-EXIT-103
LK-OPEN-104..LK-OPEN-106
LK-DELALLOC-107..LK-DELALLOC-109
LK-UNLINK-110..LK-UNLINK-112
LK-SLEEP-113..LK-SLEEP-115
LK-SIGNAL-116..LK-SIGNAL-118
LK-PIPE-119..LK-PIPE-121
LK-PIPECLOSE-122..LK-PIPECLOSE-124
LK-FUTEX-125..LK-FUTEX-127
LK-EVENTFD-128..LK-EVENTFD-130
LK-EVENTFDCLOSE-131..LK-EVENTFDCLOSE-133
LK-EPOLL-134..LK-EPOLL-136
LK-EPOLLCLOSE-137..LK-EPOLLCLOSE-139
LK-SIGNALFD-140..LK-SIGNALFD-142
LK-SIGNALFDCLOSE-143..LK-SIGNALFDCLOSE-145
LK-TIMERFD-146..LK-TIMERFD-148
LK-TIMERFDCLOSE-149..LK-TIMERFDCLOSE-151
LK-PIDFD-152..LK-PIDFD-154
LK-PIDFDCLOSE-155..LK-PIDFDCLOSE-157
LK-INOTIFY-158..LK-INOTIFY-160
LK-INOTIFYCLOSE-161..LK-INOTIFYCLOSE-163
```

最新三章：

- `LK-INOTIFYCLOSE-161`：零超时epoll_wait怎样清除inotify的stale-ready item？
- `LK-INOTIFYCLOSE-162`：inotify_rm_watch怎样先排入IN_IGNORED再销毁mark？
- `LK-INOTIFYCLOSE-163`：读取IN_IGNORED后，close怎样释放inotify group与eventpoll？

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

## 已完成inotify cleanup场景

```text
initial G.q_len=0 and level-triggered I stale-ready
→ epoll_wait(...,0) re-polls empty queue
→ remove I from EP.rdllist and return 0
→ inotify_rm_watch(6,1)
→ find M in IDR and take temporary reference
→ detach M from G.marks_list
→ clear ALIVE and call inotify freeing_mark callback
→ queue wd1 IN_IGNORED before removing IDR entry
→ G.q_len 0→1; callback P requeues I
→ remove idr[1], set M.wd=-1, decrement watch ucount
→ final active mark refs drop
→ remove M from /work inode connector and release inode pin
→ queue mark/connector storage for SRCU-safe workers
→ rm_watch returns 0
→ epoll_wait(...,0) returns EPOLLIN/data 0x494E4F36
→ read(6) copies 16-byte wd1 IN_IGNORED record and q_len becomes 0
→ EPOLL_CTL_DEL frees P and removes I; EP refcount 2→1
→ close(6) sets group shutdown and flushes mark reaper
→ mark M, overflow event, empty IDR, group G and inotify file are freed
→ close(7) drops empty EP refcount 1→0 and queues RCU free
→ fd 6/7 closed; /work/new.txt remains
```

## 当前精确状态

```text
system_state        = SYSTEM_RUNNING
current executor    = parent
CPU/mode            = CPU0, x86-64 CPL 3
parent state        = TASK_RUNNING, on_rq=1, on_cpu=1
helper              = blocked outside inotify objects
last syscall        = close(7)
last return         = 0
stale cleanup wait  = 0
rm_watch return     = 0
ignored epoll wait  = 1, EPOLLIN/data 0x494E4F36
ignored read        = 16, wd1 IN_IGNORED cookie0 len0
EPOLL_CTL_DEL       = 0
close(6)            = 0
fd 6/7              = closed
wd 1                = invalid, absent from IDR
mark M              = freed
/work connector     = detached; storage may await independent reaper
fsnotify group G    = freed
callback P          = synchronously freed
epitem I            = logically dead; RCU storage free
eventpoll EP        = logically dead; RCU storage free
/work/new.txt       = exists
global anon_inodefs = active
next entry          = unselected
```

## 必须保持的技术边界

1. eventpoll ready list与fsnotify notification queue是两套状态。
2. zero-time wait仍执行re-poll；empty queue返回0并清除stale-ready membership。
3. 清除ready membership不删除registration或callback。
4. rm_watch先取得临时mark reference，再执行detach。
5. mark先清ATTACHED并退出group list，随后清ALIVE。
6. inotify backend在IDR removal前排入`IN_IGNORED`，所以record保存wd 1。
7. event中的wd是入队快照，不受`M.wd=-1`影响。
8. callback在parent未睡眠时只让epitemready，不执行task wakeup。
9. IDR ref、group-list ref、syscall temp ref与connector attachment属于不同lifetime。
10. mark最后ref下降后才从inode connector移除。
11. watch removal归还目录inode pin，但不删除目录或文件。
12. rm_watch不等待mark/connector storage物理释放。
13. group close通过`flush_delayed_work(reaper_work)`等待mark SRCU销毁完成。
14. connector使用独立worker，close返回不保证其storage已kfree。
15. no-name `IN_IGNORED` record总长度为16字节。
16. read清空queue后epitem再次stale；DEL直接删除它。
17. callback同步free；epitem和eventpoll通过RCU释放storage。
18. inotify final group free销毁empty IDR、overflow event、instance ucount与memcg ref。
19. anon_inodefs全局对象不会因最后fd关闭而卸载。
20. cleanup不会删除`/work/new.txt`。

## 下一建议场景

```text
socketpair(AF_UNIX, SOCK_STREAM|SOCK_CLOEXEC, 0, sv)
→ fd 6/7 form a connected unix socket pair
epoll_create1(EPOLL_CLOEXEC) → fd 8
epoll_ctl(8, ADD, 6, EPOLLIN|EPOLLRDHUP)
parent epoll_wait blocks
helper write(7,"hello",5)
→ unix stream receive queue wakes epoll
parent reads 5 bytes
helper shutdown(7,SHUT_WR)
→ parent observes EPOLLRDHUP and read EOF
```

开始前固定socket state、sk_receive_queue、socket wait queue、memory accounting、shutdown flags、callback顺序与scheduler顺序。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。继续时读取`AGENTS.md`、`project/STATE.rst`、目录、最近章节和manifest；每批固定写三章并同步五份接续文件。
