第一百二十八章：eventfd2() 怎样建立counter并发布fd 6？
=====================================================

上一章结束时，private futex实验已经完成。本章开启一个独立的运行期场景，parent与helper仍是同一进程内的两个线程，并共享同一个 ``files_struct``。

parent执行：

.. code-block:: c

   int efd = eventfd2(0, EFD_CLOEXEC);

固定条件：

* CPU0是唯一online CPU；
* parent与helper都是 ``SCHED_NORMAL``；
* fd 0..5已经占用，因此新fd固定为6；
* 初始counter为0；
* 只设置 ``EFD_CLOEXEC``；
* 没有 ``EFD_NONBLOCK``；
* 没有 ``EFD_SEMAPHORE``；
* 没有seccomp、LSM拒绝、内存分配失败或fd耗尽；
* 本场景不调用poll、epoll、io_uring或内核侧 ``eventfd_signal()``。

本章结束在fd 6已经发布，指向一个可读可写的eventfd file； ``eventfd_ctx.count=0``，wait queue为空。

eventfd2怎样进入do_eventfd
---------------------------

native x86-64 syscall路径是：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_eventfd2(0, EFD_CLOEXEC)
   → do_eventfd(0, EFD_CLOEXEC)

``eventfd2`` 的第一个参数在userspace接口中是 ``unsigned int``，而内部counter是 ``__u64``。固定初值0可以无损写入64位 ``ctx->count``。

``do_eventfd`` 首先验证flags只能来自 ``EFD_FLAGS_SET``。三个用户标志与file flags的关系由build-time检查固定：

::

   EFD_CLOEXEC  == O_CLOEXEC
   EFD_NONBLOCK == O_NONBLOCK
   EFD_SEMAPHORE == 1 << 0

本场景flags合法，继续分配 ``struct eventfd_ctx``。

eventfd_ctx包含哪些状态
-----------------------

``kmalloc`` 成功后，内核初始化：

::

   kref_init(&ctx->kref)
   init_waitqueue_head(&ctx->wqh)
   ctx->count = 0
   ctx->flags = EFD_CLOEXEC

核心对象是：

.. code-block:: c

   struct eventfd_ctx {
       struct kref kref;
       wait_queue_head_t wqh;
       __u64 count;
       unsigned int flags;
       int id;
   };

这些字段分别承担不同职责：

* ``kref`` 管理ctx生命周期；
* ``wqh.lock`` 同时保护counter与wait queue；
* ``wqh.head`` 保存阻塞reader、writer或poll waiter；
* ``count`` 保存64位event counter；
* ``flags`` 保留 ``EFD_SEMAPHORE`` 等eventfd语义标志；
* ``id`` 用于fdinfo标识，不参与read/write正确性。

初始状态是：

::

   count = 0
   wait queue = empty
   kref = one file-owned reference

为什么file是O_RDWR
-----------------

``do_eventfd`` 保留共享fcntl flags后，强制加入：

.. code-block:: c

   flags |= O_RDWR;

所以同一个fd 6既允许read，也允许write。eventfd不是pipe的两个endpoint，也不会产生独立read file与write file。

固定场景最终只有：

::

   one fd number
   → one struct file
   → one eventfd_ctx

parent与helper共享fdtable，因此两者都能用fd 6访问同一个file和同一个counter。

anon_inode怎样承载eventfd file
-----------------------------

``do_eventfd`` 调用：

::

   anon_inode_getfile_fmode(
       "[eventfd]",
       &eventfd_fops,
       ctx,
       O_RDWR,
       FMODE_NOWAIT)

``anon_inode_getfile_fmode`` 复用anon-inode filesystem的singleton inode，建立一个pseudo dentry和新的 ``struct file``，随后设置：

::

   file->f_op          = &eventfd_fops
   file->private_data  = ctx
   file->f_mode       |= FMODE_NOWAIT

``eventfd_fops`` 的关键入口是：

::

   .read_iter = eventfd_read
   .write     = eventfd_write
   .poll      = eventfd_poll
   .release   = eventfd_release
   .llseek    = noop_llseek

这不是磁盘文件：

* 没有pathname lookup；
* 没有ext4 inode；
* 没有page cache数据页；
* 没有file position语义；
* 没有journal或block I/O。

``FMODE_NOWAIT`` 表示VFS允许 ``IOCB_NOWAIT`` read请求进入实现；本场景普通blocking ``read()`` 不设置该kiocb标志。

close-on-exec保存在哪里
----------------------

``EFD_CLOEXEC`` 不会变成eventfd counter语义。它由fd分配设施写入共享fdtable的 ``close_on_exec`` bitmap。

因此创建后的对象分为两层flags：

::

   ctx->flags
   → 保存eventfd创建flags

   fdtable close_on_exec bit for fd 6
   → execve时自动关闭fd

file本身仍是blocking ``O_RDWR``，因为本场景没有 ``EFD_NONBLOCK``。

fd 6怎样发布
------------

``FD_PREPARE`` 先保留最低可用fd。由于0..5已占用：

::

   reserved fd = 6

file、ctx与fd reservation都成功后，内核为ctx分配一个eventfd id，然后执行 ``fd_publish``：

::

   fdt->fd[6] = eventfd_file
   set open_fds bit 6
   set close_on_exec bit 6

publication完成后，共享这个 ``files_struct`` 的parent与helper都能通过fd 6取得同一个file。

只有到这一边界，userspace才获得稳定fd number。若此前任一步失败，准备中的file与ctx会通过错误清理路径释放，不会留下半发布fd。

eventfd2怎样返回
----------------

``fd_publish`` 返回fd number，因此：

::

   __x64_sys_eventfd2 returns 6
   → exit_to_user_mode
   → parent CPL 3, RAX=6

userspace变量 ``efd`` 现在等于6。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* syscall result/RAX：6；
* shared fd 6：open、close-on-exec；
* fd 6 access mode：``O_RDWR``；
* fd 6 blocking mode：blocking；
* ``struct file``：使用 ``eventfd_fops``；
* ``file->private_data``：eventfd ctx E；
* ctx E ``kref``：由file持有活动引用；
* ctx E ``count``：0；
* ctx E semaphore mode：disabled；
* ctx E wait queue：empty；
* ctx E waitqueue spinlock：unlocked；
* anon-inode pseudo file：active；
* page cache、filesystem与block I/O：none；
* next entry：parent ``read(6, &value, 8)``。

关键边界
--------

#. eventfd使用一个fd同时完成read与write，不像pipe那样创建两个endpoint。
#. ``eventfd_ctx`` 的counter与wait queue由同一个 ``wqh.lock`` 保护。
#. ``EFD_CLOEXEC`` 主要落实为fdtable bitmap，不会把file变成nonblocking。
#. 未设置 ``EFD_SEMAPHORE`` 时，一次成功read会取得整个counter并清零。
#. anon-inode file不对应磁盘文件，也不触发journal或block I/O。
#. fd publication之前发生错误不会向userspace泄漏半初始化对象。

下一入口
--------

parent将执行：

.. code-block:: c

   uint64_t value = 0;
   read(6, &value, sizeof(value));

此时counter仍为0，因此下一章进入 ``eventfd_read`` 的locked wait queue路径。

资料
----

* `Linux 7.2-rc1 fs/eventfd.c：eventfd_ctx、do_eventfd与eventfd2 syscall <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventfd.c>`_
* `Linux 7.2-rc1 fs/anon_inodes.c：anon_inode_getfile_fmode与pseudo file建立 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/anon_inodes.c>`_
* `Linux 7.2-rc1 include/linux/file.h：FD_PREPARE与fd publication设施 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/file.h>`_
