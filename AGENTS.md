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
```

最新三章：

- `LK-INOTIFY-158`：inotify怎样建立目录watch并让parent阻塞在epoll_wait？
- `LK-INOTIFY-159`：helper创建并关闭new.txt时，fsnotify怎样排入两条inotify事件？
- `LK-INOTIFY-160`：parent怎样从epoll event读取两条inotify_event记录？

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

## 已完成inotify场景

```text
inotify_init1(IN_CLOEXEC) -> fd 6
→ fsnotify group G with empty notification queue
→ inotify_add_watch(/work, IN_CREATE|IN_CLOSE_WRITE) -> wd 1
→ mark M mask includes CREATE, CLOSE_WRITE, UNMOUNT and EVENT_ON_CHILD
→ epoll_create1 -> fd 7
→ ADD attaches callback P to G.notification_waitq
→ parent waits exclusively on EP.wq and schedules out
→ helper openat creates /work/new.txt as fd 8
→ fsnotify_create queues wd1 IN_CREATE name new.txt
→ P links one epitem I and wakes parent
→ helper write produces unrequested MODIFY hook, no user record
→ helper close queues wd1 IN_CLOSE_WRITE name new.txt
→ mask differs from queue tail, so no merge
→ parent epoll_wait re-polls q_len=2 and returns EPOLLIN/data 0x494E4F36
→ level-triggered I requeues
→ parent read(6,buf,4096)
→ copies two FIFO records, each 32 bytes
→ read returns 64 and G.q_len becomes 0
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
current executor   = parent
CPU/mode           = CPU0, x86-64 CPL 3
parent state       = TASK_RUNNING, on_rq=1, on_cpu=1
helper              = blocked outside inotify objects
epoll_wait return  = 1
epoll event         = EPOLLIN, data 0x494E4F36
read return         = 64
record 0            = wd1 IN_CREATE cookie0 len16 name new.txt
record 1            = wd1 IN_CLOSE_WRITE cookie0 len16 name new.txt
fd 6                = open blocking inotify file
fsnotify group G    = active, q_len=0
watch wd1 / mark M = active on /work inode
group wait queue    = epoll callback P only
fd 7                = open eventpoll file
EP refcount         = 2
EP rbr              = contains I
EP rdllist          = contains stale-ready I
EP wq               = empty
/work/new.txt       = exists
fd 8                = closed
next entry          = unselected
```

## 必须保持的技术边界

1. inotify file的`private_data`是`fsnotify_group`，不是watched directory file。
2. group notification queue与eventpoll ready list是两套不同队列。
3. directory mark自动加入`FS_EVENT_ON_CHILD|FS_UNMOUNT`。
4. 新group首个watch descriptor由IDR从1分配。
5. callback P位于`G.notification_waitq`，sleeping parent W位于`EP.wq`。
6. create成功后才调用`fsnotify_create`。
7. 未订阅`IN_MODIFY`时，write hook不会生成用户record。
8. `IN_CLOSE_WRITE`由file write mode选择，不保证fsync或durability。
9. inotify merge只比较queue最后一条，且要求mask/wd/name全部相同。
10. create与close-write不会合并，FIFO顺序保持。
11. 多条notification records只产生一个fd-level epitem readiness。
12. `FS_EVENT_ON_CHILD`是内部route bit，不输出到userspace mask。
13. `struct inotify_event`头为16字节；`new.txt` padded name area为16字节。
14. 两条record总read长度为64。
15. read清空queue不会主动清除epoll ready membership。
16. read event不会删除watch。

## 下一建议场景

```text
epoll_wait(7, events2, 1, 0)
→ re-poll empty queue and remove stale-ready I
→ return 0
inotify_rm_watch(6, 1)
→ mark destruction queues IN_IGNORED
→ remove wd 1 from IDR and decrement watch ucount
→ callback makes I ready again
epoll_wait(7, events3, 1, 0)
→ deliver EPOLLIN
read(6)
→ consume one 16-byte IN_IGNORED record with len 0
EPOLL_CTL_DEL
→ remove P and I
close(6), close(7)
→ destroy group and eventpoll
```

开始前固定mark destroy worker、`IN_IGNORED`排队时序、mark references、group shutdown、queue flush与eventpoll teardown顺序。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。继续时读取`AGENTS.md`、`project/STATE.rst`、目录、最近章节和manifest；每批固定写三章并同步五份接续文件。
