第一百一十九章：pipe2() 怎样建立匿名管道并发布 fd 6/7？
============================================================

上一场景已经结束。现在开始一个独立运行期实验，不继承上一场景中helper process的对象关系。

固定环境：

* 系统只有CPU0 online；
* 当前进程包含parent与helper两个 ``SCHED_NORMAL`` 线程；
* 两个线程共享同一个 ``files_struct``，因此共享fd table；
* parent当前运行在CPU0，helper已经runnable，但在本章不会抢先执行；
* fd 0到5已经占用；
* userspace ``pipefd[2]`` 可写；
* userspace调用 ``pipe2(pipefd, O_CLOEXEC)``；
* 没有 ``O_NONBLOCK``、``O_DIRECT`` 或 ``O_NOTIFICATION_PIPE``；
* page size为4096 bytes；
* 当前user没有pipe quota压力，所有slab、inode、file与fd分配均成功。

本章结束时，匿名pipe已经建立，read end发布为fd 6，write end发布为fd 7，``pipefd`` 中得到 ``{6, 7}``，但pipe仍为空。

syscall 怎样进入 do_pipe2
-------------------------

native x86-64 userspace进入：

.. code-block:: c

   int pipefd[2];
   int ret = pipe2(pipefd, O_CLOEXEC);

控制流是：

.. code-block:: text

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_pipe2
   → do_pipe2(pipefd, O_CLOEXEC)

``do_pipe2()`` 先在kernel stack准备：

.. code-block:: c

   struct file *files[2];
   int fd[2];

它不会先把任何fd写进userspace，也不会先修改fd table。第一步是：

.. code-block:: text

   __do_pipe_flags(fd, files, O_CLOEXEC)

``__do_pipe_flags()`` 验证flags。``O_CLOEXEC`` 在允许集合中；固定场景没有packet mode、nonblocking mode或watch queue。

pipefs inode 与 pipe_inode_info 怎样建立
---------------------------------------

对象创建从：

.. code-block:: text

   create_pipe_files
   → get_pipe_inode
   → new_inode_pseudo(pipe_mnt->mnt_sb)
   → alloc_pipe_info

开始。

这里的inode属于内部 ``pipefs`` pseudo filesystem。它没有磁盘目录项，也不会触发ext4、block layer或设备I/O。

``alloc_pipe_info()`` 分配一个清零的 ``struct pipe_inode_info``。固定user没有超过soft/hard pipe page quota，因此采用默认：

.. code-block:: text

   PIPE_DEF_BUFFERS = 16
   ring_size        = 16 slots
   max_usage        = 16 slots
   capacity         = 16 * 4096 = 65536 bytes

这里先分配的是16个 ``struct pipe_buffer`` 组成的ring metadata。并没有同时分配16个data page；真正的匿名data page会在write需要新slot时按需分配。

清零与初始化后，关键状态是：

.. code-block:: text

   head             = 0
   tail             = 0
   occupancy        = 0
   rd_wait           = initialized
   wr_wait           = initialized
   tmp_page[0..1]    = NULL
   r_counter         = 1
   w_counter         = 1
   mutex             = initialized

``get_pipe_inode()`` 把pipe挂到pseudo inode：

.. code-block:: text

   inode->i_pipe     = pipe
   pipe->files       = 2
   pipe->readers     = 1
   pipe->writers     = 1
   inode->i_fop      = pipeanon_fops
   inode->i_mode     = S_IFIFO | 0600

``files=2`` 表示即将有两个 ``struct file`` 引用这个pipe。``readers=1`` 和 ``writers=1`` 表示read side与write side都存在，它们不是当前正在执行read/write syscall的线程数量。

两个 struct file 怎样指向同一pipe
---------------------------------

``create_pipe_files()`` 先建立write end：

.. code-block:: text

   alloc_file_pseudo(..., O_WRONLY, &pipeanon_fops)
   → write_file

随后通过 ``alloc_file_clone()`` 建立read end：

.. code-block:: text

   alloc_file_clone(write_file, O_RDONLY, &pipeanon_fops)
   → read_file

两个file都满足：

.. code-block:: text

   file->private_data = pipe
   file->f_op          = &pipeanon_fops

区别在于：

.. code-block:: text

   read_file  → FMODE_READ
   write_file → FMODE_WRITE

``pipeanon_fops`` 的核心dispatch是：

.. code-block:: text

   .read_iter  = anon_pipe_read
   .write_iter = anon_pipe_write
   .poll       = pipe_poll
   .release    = pipe_release

``stream_open()`` 把两端标记为stream。pipe没有普通文件的seek position；后续read/write不会推进有意义的 ``f_pos``。

fd 6/7 为什么先保留、后发布
--------------------------

file对象建立完成后，``__do_pipe_flags()`` 连续调用：

.. code-block:: text

   get_unused_fd_flags(O_CLOEXEC) → 6
   get_unused_fd_flags(O_CLOEXEC) → 7

此时fd 6和7已经在共享fd table中被保留，防止并发fd分配者取得相同编号；对应file pointer尚未通过 ``fd_install()`` 发布。

``O_CLOEXEC`` 设置的是fd table中的close-on-exec位。它不把read/write end变成nonblocking，也不是pipe file本身的数据路径flag。

返回数组暂存在kernel stack：

.. code-block:: text

   fd[0] = 6   read end
   fd[1] = 7   write end

``do_pipe2()`` 接着执行：

.. code-block:: text

   copy_to_user(pipefd, {6, 7}, sizeof(fd))

固定copy成功后，才真正发布：

.. code-block:: text

   fd_install(6, read_file)
   fd_install(7, write_file)

先copy、后install的顺序使 ``copy_to_user`` 失败时可以释放file并撤销reserved fd，不会把userspace不知道的pipe端点遗留在fd table里。

parent 怎样返回用户态
---------------------

``do_pipe2()`` 返回0，syscall exit把结果放入RAX。parent回到CPL 3：

.. code-block:: text

   ret       = 0
   pipefd[0] = 6
   pipefd[1] = 7

由于parent与helper共享 ``files_struct``，fd 6/7对两个线程同时可见。这里没有复制file object；fd table中的两个slot分别持有read_file与write_file。

当前精确状态
------------

* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* ``pipe2`` result/RAX：0；
* shared fd table：fd 6为read end，fd 7为write end；
* fd 6/7 close-on-exec bit：set；
* ``pipe->files``：2；
* ``pipe->readers``：1；
* ``pipe->writers``：1；
* ring size/max usage：16 slots；
* byte capacity：65536；
* ``head=0``、``tail=0``、occupancy=0；
* data pages：0；
* ``tmp_page[0]=tmp_page[1]=NULL``；
* reader/writer wait queues：empty；
* helper：runnable，共享fd table，尚未执行write；
* next entry：parent调用 ``read(6, buf, 5)``。

关键边界
--------

#. anonymous pipe由pipefs pseudo inode承载，不是磁盘文件。
#. ring在创建时分配 ``pipe_buffer`` metadata，data page按write需求分配。
#. ``readers/writers`` 记录open endpoint数量，不记录正在syscall中的线程数量。
#. read end与write end是两个 ``struct file``，共享一个 ``pipe_inode_info``。
#. ``FMODE_STREAM`` 使pipe read/write没有普通文件position语义。
#. ``O_CLOEXEC`` 属于descriptor publication状态，不等于 ``O_NONBLOCK``。
#. fd先reserved，userspace数组copy成功后才 ``fd_install``。
#. helper因为共享 ``files_struct``，不需要再次传递或dup fd 6/7。

资料
----

* `Linux 7.2-rc1 fs/pipe.c：alloc_pipe_info、get_pipe_inode、create_pipe_files与pipe2 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pipe.c>`_
* `Linux 7.2-rc1 include/linux/pipe_fs_i.h：pipe ring、pipe_buffer与默认slot数量 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/pipe_fs_i.h>`_
* `Linux 7.2-rc1 fs/file.c：get_unused_fd_flags与fd_install所使用的fd table机制 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file.c>`_
