第一百五十九章：helper创建并关闭new.txt时，fsnotify怎样排入两条inotify事件？
================================================================================

上一章结束时，parent阻塞在eventpoll ``EP.wq``，helper运行于CPU0。inotify group ``G`` 的notification queue为空，epoll callback ``P`` 已经挂在 ``G.notification_waitq``。

helper依次执行：

.. code-block:: c

   int fd = openat(AT_FDCWD, "/work/new.txt",
                   O_CREAT | O_WRONLY | O_TRUNC, 0644); /* fd 8 */
   write(fd, "data", 4);
   close(fd);

本章固定条件：

* parent与helper共享 ``files_struct``；
* fd 0..7已占用，因此helper获得fd 8；
* ``new.txt`` 初始不存在；
* ext4 create、write与close全部成功；
* 写入4字节只走普通buffered write，本章不要求 ``fsync`` 或存储持久化；
* watch只订阅 ``IN_CREATE|IN_CLOSE_WRITE``，没有 ``IN_OPEN``、 ``IN_MODIFY`` 或 ``IN_ATTRIB``；
* helper被唤醒parent后不会立刻被抢占；在固定调度顺序中，helper完成write与close后才阻塞在inotify之外；
* event allocation成功，queue不overflow；
* 没有其他目录事件、rename、unlink、signal或并发reader。

本章结束在两条事件按顺序位于 ``G.notification_list``：第一条 ``IN_CREATE``，第二条 ``IN_CLOSE_WRITE``。parent已经runnable，helper在对象外阻塞，scheduler将恢复parent原来的 ``epoll_wait`` 内核栈。

openat创建文件后，谁发出CREATE事件
---------------------------------

helper从CPL 3进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_openat
   → do_sys_openat2
   → do_filp_open
   → path_openat
   → ext4 create/open path

固定 ``new.txt`` 不存在，成功create后VFS到达：

::

   fsnotify_create(/work inode D, new.txt dentry C)

对于支持atomic open的filesystem，这一调用发生在file已经带有 ``FMODE_CREATED`` 的成功open分支；普通 ``vfs_create`` 分支也在create成功后调用同一个hook。两种实现边界的共同事实是：只有名称已经成功连接到目录后，VFS才提交 ``FS_CREATE`` notification。

``fsnotify_create`` 执行：

::

   fsnotify_dirent(D, C, FS_CREATE)
   → fsnotify_name(FS_CREATE,
                   C,
                   FSNOTIFY_EVENT_DENTRY,
                   D,
                   &C->d_name,
                   cookie=0)

目录inode ``D`` 上存在mark ``M``，且 ``M.mask`` 包含 ``FS_CREATE``，因此fsnotify core把事件交给inotify group ``G``。

CREATE事件怎样变成inotify_event_info
------------------------------------

fsnotify调用inotify backend：

::

   inotify_handle_inode_event(M, FS_CREATE,
                               child inode,
                               dir D,
                               name "new.txt",
                               cookie 0)

``M.wd`` 仍为1。名称长度固定为：

::

   strlen("new.txt") = 7

inotify分配：

::

   sizeof(struct inotify_event_info) + 7 + 1

的新event ``Ecreate``，并填入：

::

   Ecreate.mask        = FS_CREATE
   Ecreate.wd          = 1
   Ecreate.sync_cookie = 0
   Ecreate.name_len    = 7
   Ecreate.name        = "new.txt\0"

create不是move pair，不需要sync cookie，因此cookie为0。

第一条事件怎样进入queue
-----------------------

``inotify_handle_inode_event`` 调用：

::

   fsnotify_add_event(G, Ecreate, inotify_merge)
   → fsnotify_insert_event

在 ``G.notification_lock`` 下检查：

::

   G.shutdown = false
   G.q_len     = 0 < G.max_events
   notification_list is empty

队列为空，不调用merge比较。随后：

::

   G.q_len: 0 → 1
   list_add_tail(Ecreate)

释放 ``notification_lock`` 后，fsnotify执行：

::

   wake_up(&G.notification_waitq)

wait queue中只有epoll callback ``P``。这个wake没有携带精确poll mask key， ``P`` 因而把它视为“目标file可能ready”，进入 ``ep_poll_callback``。

callback怎样让parent runnable
----------------------------

``P`` 取得eventpoll ``EP`` 的IRQ-safe spinlock，发现epitem ``I`` 尚未在ready list，于是：

::

   EP.rdllist: empty → [I]

随后唤醒 ``EP.wq`` 上的exclusive waiter ``W``：

::

   parent TASK_INTERRUPTIBLE → TASK_RUNNING
   parent on_rq             0 → 1

``W`` 仍然位于parent的内核栈上，直到parent真正恢复并完成wait cleanup。

wake不等于立即切换CPU。固定本章没有强制reschedule点，因此helper继续执行。

write为什么没有排入第三条事件
-----------------------------

helper的 ``write(8, "data", 4)`` 进入ext4 buffered write，并会触发文件修改类fsnotify hook：

::

   fsnotify_modify(F8)
   → FS_MODIFY

``fsnotify_parent`` 可以找到watched parent ``/work``，但最终mark interest检查要求：

::

   event mask & M.mask & ALL_FSNOTIFY_EVENTS

``M.mask`` 不包含 ``FS_MODIFY``，因此inotify backend不会为这次write分配或排入用户event。

所以“filesystem产生过modify hook”与“当前inotify fd收到IN_MODIFY record”是两个不同事实。本固定watch没有订阅它，queue仍只有一条CREATE事件。

close为什么生成CLOSE_WRITE
--------------------------

helper执行 ``close(8)``。fd 8是该file ``F8`` 的最后reference，用户close同步进入 ``__fput(F8)``。

通用file teardown开头调用：

::

   fsnotify_close(F8)

``fsnotify_close`` 根据：

::

   F8->f_mode & FMODE_WRITE

选择mask：

::

   FS_CLOSE_WRITE

它不是根据“是否真的写入了至少一个字节”判断；只要file以write mode打开，close事件类型就是CLOSE_WRITE。本场景确实写入4字节，但该事实不是mask选择条件。

close event怎样找到父目录mark
-----------------------------

调用链是：

::

   fsnotify_close(F8)
   → fsnotify_file(F8, FS_CLOSE_WRITE)
   → fsnotify_path(&F8->f_path, FS_CLOSE_WRITE)
   → fsnotify_parent(new.txt dentry,
                     FS_CLOSE_WRITE,
                     path,
                     FSNOTIFY_EVENT_PATH)

``new.txt`` dentry已经带有 ``DCACHE_FSNOTIFY_PARENT_WATCHED``，fsnotify取得父dentry和目录inode ``D``，检查：

::

   M.mask includes FS_EVENT_ON_CHILD
   M.mask includes FS_CLOSE_WRITE

所以它截取稳定的dentry name snapshot，并把内部mask扩展为：

::

   FS_CLOSE_WRITE | FS_EVENT_ON_CHILD

``FS_EVENT_ON_CHILD`` 只用于内核路由；最终inotify用户mask不会暴露该内部bit。

第二条事件怎样入队
------------------

inotify backend建立 ``Eclose``：

::

   Eclose.mask        = FS_CLOSE_WRITE | FS_EVENT_ON_CHILD
   Eclose.wd          = 1
   Eclose.sync_cookie = 0
   Eclose.name_len    = 7
   Eclose.name        = "new.txt\0"

queue当前已有 ``Ecreate``。inotify merge只把新事件与queue最后一条比较，且要求以下字段全部相同：

::

   mask
   wd
   name_len
   name bytes

两条事件的mask不同：

::

   FS_CREATE != FS_CLOSE_WRITE | FS_EVENT_ON_CHILD

因此不合并。 ``fsnotify_insert_event`` 在 ``G.notification_lock`` 下执行：

::

   G.q_len: 1 → 2
   G.notification_list:
       [ Ecreate, Eclose ]

第二次 ``wake_up(&G.notification_waitq)`` 会再次运行callback ``P``。此时 ``I`` 已经链接在 ``EP.rdllist``，callback不会重复插入同一个epitem，也不会产生第二个用户epoll event slot。

两个inotify records与一个epoll readiness的关系
---------------------------------------------

此时对象关系为：

::

   inotify queue = two records
   epoll ready list = one epitem

Epoll追踪的是“fd当前是否可读”，不按notification record数量建立多个epitem。只要queue从空变为非空，fd就是readable；后续继续排入事件只维持readable状态。

helper怎样让出CPU
-----------------

``close(8)`` 完成后：

* fd 8从共享fdtable撤销；
* ``F8`` 完成通用file teardown；
* 新ext4文件仍通过目录名称存在；
* ``IN_CLOSE_WRITE`` 已经排入queue；
* 数据是否持久化到存储设备不由close-write notification保证。

固定helper随后阻塞在inotify对象之外。scheduler在CPU0上选择已经runnable的parent，并恢复parent暂停的 ``epoll_wait`` 内核栈。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent即将恢复，scheduler切换完成点位于parent kernel stack；
* CPU：CPU0；
* CPU mode：x86-64 CPL 0；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* helper：阻塞在inotify之外；
* helper ``openat`` result：8；
* helper ``write`` result：4；
* helper ``close(8)`` result：0；
* ``/work/new.txt``：存在，普通ext4 regular file；
* fd 8：closed；
* inotify group ``G.q_len``：2；
* ``G.notification_list[0]``：wd1、 ``FS_CREATE``、cookie0、name ``new.txt``；
* ``G.notification_list[1]``：wd1、 ``FS_CLOSE_WRITE|FS_EVENT_ON_CHILD``、cookie0、name ``new.txt``；
* overflow event：未排队；
* directory mark ``M``：仍active；
* ``G.notification_waitq``：仍包含epoll callback ``P``；
* eventpoll ``EP.rdllist``：包含一个epitem ``I``；
* ``EP.wq``：仍包含parent栈waiter ``W``，等待恢复后的cleanup；
* filesystem durability：未由本章保证；
* next control entry：parent从 ``schedule()`` 返回，完成 ``epoll_wait`` event delivery。

关键边界
--------

#. CREATE notification只在目录项成功创建后提交。
#. create与close-write使用同一个wd和name，但mask不同，因此不会合并。
#. inotify只比较queue尾部进行相邻重复事件合并。
#. 未订阅 ``IN_MODIFY`` 时，write hook不会形成用户record。
#. CLOSE_WRITE由file的write mode决定，不是持久化完成通知。
#. child close事件通过 ``FS_EVENT_ON_CHILD`` 路由到父目录mark。
#. ``FS_EVENT_ON_CHILD`` 是内部路由bit，不会作为用户inotify mask输出。
#. notification queue保存两个event，eventpoll ready list只保存一个epitem。
#. 第一次wake把parent变为runnable；第二次wake不会重复链接同一个epitem。
#. wakeup不强制立即CPU handoff，固定helper完成close后才阻塞。

下一任务
--------

下一章由parent完成：

::

   epoll_wait returns {EPOLLIN, data=0x494E4F36}
   → read(6, buf, 4096)
   → copy first 32-byte IN_CREATE record
   → copy second 32-byte IN_CLOSE_WRITE record
   → return 64
   → notification queue becomes empty

资料
----

* `Linux 7.2-rc1 fsnotify.h：create、modify、close与parent路由hooks <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/fsnotify.h>`_
* `Linux 7.2-rc1 fsnotify.c：parent/name路由与mark interest检查 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/notify/fsnotify.c>`_
* `Linux 7.2-rc1 inotify_fsnotify.c：event allocation、merge与queue提交 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/notify/inotify/inotify_fsnotify.c>`_
* `Linux 7.2-rc1 notification.c：notification list插入与wait queue wake <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/notify/notification.c>`_
