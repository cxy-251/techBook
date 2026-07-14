第一百二十二章：close(7) 怎样撤销 write end 并把 writers 降为 0？
================================================================================

上一章结束时，anonymous pipe 已经重新变空，但两个endpoint仍然打开：

::

   fd 6 → read struct file
   fd 7 → write struct file

   pipe->readers = 1
   pipe->writers = 1
   pipe->files   = 2
   pipe->head    = 1
   pipe->tail    = 1
   occupancy     = 0
   tmp_page[0]   = Q

现在helper thread执行：

.. code-block:: c

   close(7);

固定条件：

* parent与helper属于同一个thread group，并通过 ``CLONE_FILES`` 共享同一个 ``files_struct``；
* CPU0是唯一online CPU；
* helper当前在CPU0运行，parent暂时不运行；
* fd 7没有 ``dup``、SCM_RIGHTS、epoll、io_uring或其他额外file引用；
* helper之前的 ``write(7, "hello", 5)`` 已经完全返回；
* pipe当前为空，``rd_wait`` 与 ``wr_wait`` 都没有waiter；
* 没有signal、close error或并发fd操作。

本章结束在helper已经从共享fd table撤销fd 7，write-side ``struct file`` 已同步释放，而read end fd 6仍保持打开。

close syscall 先撤销fd publication
---------------------------------

native x86-64控制流进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_close(7)

``SYSCALL_DEFINE1(close)`` 首先调用：

.. code-block:: c

   file = file_close_fd(7);

``file_close_fd()`` 对当前共享的 ``files_struct`` 获取：

::

   files->file_lock

在锁内，``file_close_fd_locked()`` 读取fdtable并执行：

::

   file = fdt->fd[7]
   fdt->fd[7] = NULL
   clear fd 7 open bookkeeping
   update files->next_fd when needed

然后释放 ``files->file_lock``，把原write-side ``struct file *`` 返回给close syscall。

这里的控制边界非常明确：

* fd 7 publication已经撤销；
* write-side file object仍然存在，因为close syscall手里还持有从fdtable取出的那一个引用；
* 另一个共享该 ``files_struct`` 的thread从此也无法再通过fd 7取得该file。

因此，thread共享fd table时，不存在“helper只关闭自己的fd 7”这种语义。fd number属于共享fdtable，不属于单个thread。

为什么pipe release在close返回前同步执行
--------------------------------------

close随后调用：

::

   filp_flush(write_file, current->files)
   → fput_close_sync(write_file)

``pipeanon_fops`` 没有专用 ``flush`` callback，所以固定场景的 ``filp_flush()`` 返回0。

``fput_close_sync()`` 使用针对最后一个close引用优化的refcount下降：

.. code-block:: c

   if (file_ref_put_close(&file->f_ref))
       __fput(file);

固定write-side file没有其他引用，因此refcount降到最后一个引用，``__fput()`` 在helper当前syscall上下文中同步执行。它不会排到task_work，也不会等helper以后返回用户态才处理。

``__fput()`` 的关键顺序是：

::

   fsnotify_close
   → eventpoll_release
   → locks_remove_file
   → security_file_release
   → file->f_op->release
   → dput(file->f_path.dentry)
   → mntput(file->f_path.mnt)
   → file_free

对anonymous pipe，``file->f_op->release`` 指向 ``pipe_release()``。

pipe_release 怎样把 writers 变成 0
---------------------------------

helper进入 ``pipe_release(inode, write_file)`` 后，先获取：

::

   pipe->mutex

write-side file的 ``f_mode`` 包含 ``FMODE_WRITE``，不包含 ``FMODE_READ``，因此：

::

   pipe->writers: 1 → 0
   pipe->readers: 保持 1

随后 ``pipe_release()`` 检查：

.. code-block:: c

   if (!pipe->readers != !pipe->writers) {
       wake_up_interruptible_all(&pipe->rd_wait);
       wake_up_interruptible_all(&pipe->wr_wait);
       ...
   }

此时：

::

   !readers = false
   !writers = true

两者不同，说明一侧endpoint刚刚消失，而另一侧仍存在。内核会wake两个wait queue：

* 睡在空pipe上的reader需要发现 ``writers==0``，从而返回EOF；
* 睡在满pipe上的writer需要发现 ``readers==0``，从而返回 ``-EPIPE`` 或处理SIGPIPE。

固定场景当前没有waiter，所以这次wake不会让任何task变为runnable。wake操作仍然执行，因为endpoint计数变化本身决定了通知条件。

files 为什么只从 2 降到 1
-------------------------

``pipe_release()`` 解锁 ``pipe->mutex`` 后调用：

::

   put_pipe_info(inode, pipe)

该函数获取 ``inode->i_lock`` 并执行：

::

   pipe->files: 2 → 1

``files`` 统计的是引用此 ``pipe_inode_info`` 的pipe endpoint file objects，不是fdtable中当前有多少数字，也不是thread数量。

因为read-side file仍然存在：

::

   pipe->files != 0

所以本次不会调用 ``free_pipe_info()``：

* 16-slot ring仍存在；
* ``pipe_inode_info`` 仍存在；
* ``tmp_page[0]`` 中的page Q仍保留；
* pipefs pseudo inode仍由read-side path引用。

write-side ``__fput()`` 随后释放它自己的pseudo dentry/path引用和file object。read-side file持有的另一份path引用仍让pipefs对象保持可达。

close(7) 怎样返回
-----------------

``fput_close_sync()`` 完成后，``__x64_sys_close`` 检查之前的 ``filp_flush`` result。固定result为0，因此helper返回用户态：

::

   RAX = 0

fd 7在close返回前已经无法访问，write-side ``struct file`` 也已经销毁。

当前精确状态
------------

* current executor：helper；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* helper close result/RAX：0；
* shared fd 7：closed，fdtable slot为NULL；
* shared fd 6：open anonymous pipe read end；
* fd 6 close-on-exec：仍设置；
* ``pipe->files``：1；
* ``pipe->readers``：1；
* ``pipe->writers``：0；
* ``head=1``、``tail=1``、occupancy=0；
* active ``pipe_buffer``：0；
* page Q：仍缓存于 ``tmp_page[0]``；
* ``pipe->mutex``：unlocked；
* ``rd_wait`` / ``wr_wait``：无waiter；
* read-side file、pseudo dentry、pseudo inode与pipe object：仍存在；
* next executor：parent将在CPU0运行并调用 ``read(6, eofbuf, 5)``。

关键边界
--------

#. ``file_close_fd`` 先撤销fd publication，再处理file object的最后引用。
#. 共享 ``files_struct`` 意味着close一个fd对整个thread group的共享fdtable生效。
#. 用户态close使用 ``fput_close_sync``；最后一次 ``__fput`` 在close返回前完成。
#. ``writers`` 在 ``pipe_release`` 中下降，不是在fdtable slot清空瞬间下降。
#. endpoint一侧变为0时，pipe会wake partner wait queues，即使固定场景当前没有waiter。
#. ``writers==0`` 不等于pipe object已经释放；read endpoint仍持有 ``files==1``。
#. 缓存page Q仍属于pipe，只有最后一个endpoint释放时才会被最终释放。

资料
----

* `Linux 7.2-rc1 fs/open.c：close syscall与fput_close_sync <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/open.c>`_
* `Linux 7.2-rc1 fs/file.c：file_close_fd_locked与共享fdtable撤销 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file.c>`_
* `Linux 7.2-rc1 fs/file_table.c：__fput与同步close引用释放 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file_table.c>`_
* `Linux 7.2-rc1 fs/pipe.c：pipe_release与put_pipe_info <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pipe.c>`_
