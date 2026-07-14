第一百二十三章：空管道在 writers=0 时，read() 为什么直接返回 EOF？
================================================================================

上一章结束时，fd 7已经从共享fdtable关闭，write-side file也已经同步释放。pipe当前状态是：

::

   fd 6          = open read end
   fd 7          = closed
   readers       = 1
   writers       = 0
   files         = 1
   head          = 1
   tail          = 1
   occupancy     = 0
   tmp_page[0]   = Q

parent现在在CPU0执行：

.. code-block:: c

   char eofbuf[5] = {'X', 'X', 'X', 'X', 'X'};
   ssize_t n = read(6, eofbuf, 5);

固定条件：

* parent与helper仍共享同一个 ``files_struct``；
* helper已经完成 ``close(7)``，不会重新打开或dup write end；
* fd 6是blocking stream read endpoint，没有 ``O_NONBLOCK``；
* pipe ring为空；
* 没有pending signal、watch queue、packet mode或copy fault；
* ``eofbuf`` 可写，但本次EOF路径不会向它复制任何字节。

本章结束在 ``read(6, eofbuf, 5)`` 返回0，用户buffer保持不变，pipe与read endpoint仍然存在。

read syscall 怎样找到stream file
--------------------------------

native x86-64调用链是：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_read(6, eofbuf, 5)
   → ksys_read

``ksys_read()`` 从共享fdtable取得fd 6对应的read-side ``struct file``。该file仍然有效，且包含：

::

   f_mode includes FMODE_READ | FMODE_CAN_READ | FMODE_STREAM
   f_op   = pipeanon_fops

``file_ppos()`` 发现 ``FMODE_STREAM``，返回NULL。因此pipe read没有普通文件的 ``f_pos`` 更新，也不存在“EOF发生在offset 1”之类的文件位置语义。

随后：

::

   vfs_read
   → new_sync_read
   → pipeanon_fops.read_iter
   → anon_pipe_read

为什么 empty 不一定等于 EOF
---------------------------

``anon_pipe_read()`` 先锁住：

::

   pipe->mutex

然后读取：

::

   head = 1
   tail = 1

``pipe_empty(head, tail)`` 为true，因此没有 ``pipe_buffer`` 可以消费。

接下来的判断顺序很关键：

.. code-block:: c

   if (!pipe->writers)
       break;
   if (ret)
       break;
   if (O_NONBLOCK)
       return -EAGAIN;
   wait_event_interruptible_exclusive(...);

上一批阻塞read发生时，pipe也是empty，但当时：

::

   writers = 1

内核知道未来仍可能有writer放入数据，所以blocking reader加入 ``rd_wait`` 并睡眠。

本次：

::

   writers = 0

这表示所有write endpoint都已关闭。对于pipe stream，内核已经能够确定：

* 当前没有未读数据；
* 未来也不可能再通过现有pipe对象产生数据。

因此 ``!pipe->writers`` 立即成立，read loop直接结束。

EOF 为什么用返回值 0 表示
------------------------

``anon_pipe_read()`` 在进入loop前设置：

::

   ret = 0

本次没有复制任何buffer，也没有设置error。遇到 ``writers==0`` 后直接break，因此最终ret仍为0。

这就是pipe EOF：

::

   read result = 0 bytes

它不是：

* ``-EAGAIN``：该值表示nonblocking pipe暂时没有数据，但writer仍可能存在；
* ``-EPIPE``：该值属于writer在没有reader时执行write；
* ``-ERESTARTSYS``：该值来自阻塞wait被signal中断；
* 5个零字节：EOF不会向用户buffer写入内容。

为什么本次完全不进入wait queue
------------------------------

等待条件 ``pipe_readable(pipe)`` 定义为：

::

   ring non-empty OR writers == 0

当前 ``writers==0``，条件本来就为true。更直接地说，``anon_pipe_read()`` 已在持有mutex时通过 ``!pipe->writers`` break，因此不会执行：

::

   mutex_unlock
   wait_event_interruptible_exclusive(rd_wait, pipe_readable(pipe))
   schedule

所以本次read：

* 不创建wait queue entry；
* 不把parent设置为 ``TASK_INTERRUPTIBLE``；
* 不调用scheduler；
* 不发生wakeup；
* 从syscall入口到返回都由parent连续执行。

用户buffer为什么保持 XXXXX
--------------------------

数据copy只发生在ring非空分支：

::

   copy_page_to_iter(buf->page, buf->offset, chars, to)

本次没有active ``pipe_buffer``，所以该函数不被调用。固定 ``eofbuf`` 在syscall前是：

::

   {'X','X','X','X','X'}

read返回后仍是相同5个字节。返回0只是在API层表达EOF，不会清空调用者提供的memory。

pipe内部状态为什么没有变化
--------------------------

read loop结束后：

* pipe仍为空，因此 ``wake_next_reader`` 保持false；
* 没有从full变为non-full，因此 ``wake_writer`` 保持false；
* ``pipe->mutex`` 被释放；
* 没有wait queue wake；
* ring head和tail都不移动；
* page Q仍在 ``tmp_page[0]``。

``vfs_read()`` 只在ret大于0时增加实际读取字节accounting。EOF ret=0不会被记成读取了5字节。

read 怎样返回用户态
-------------------

控制流按原路径退出：

::

   anon_pipe_read returns 0
   → new_sync_read returns 0
   → vfs_read returns 0
   → ksys_read returns 0
   → __x64_sys_read returns 0
   → exit_to_user_mode

parent回到CPL 3：

::

   RAX = 0
   n   = 0

这次返回说明stream已到达EOF，但它没有自动关闭read endpoint。fd 6仍然发布在fdtable中，pipe object也仍由该file引用。

当前精确状态
------------

* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* read result/RAX：0；
* semantic result：EOF；
* ``eofbuf``：仍为 ``"XXXXX"``；
* fd 6：open anonymous pipe read end，close-on-exec；
* fd 7：closed；
* ``pipe->files``：1；
* ``pipe->readers``：1；
* ``pipe->writers``：0；
* ``head=1``、``tail=1``、occupancy=0；
* active ``pipe_buffer``：0；
* page Q：仍缓存于 ``tmp_page[0]``；
* wait queue entry：本次没有创建；
* scheduling：本次read没有schedule；
* pipefs pseudo inode/dentry：仍存在；
* next syscall：parent ``close(6)``。

关键边界
--------

#. pipe empty只描述当前ring没有数据，不能单独决定阻塞或EOF。
#. ``empty && writers>0`` 的blocking read会等待未来数据。
#. ``empty && writers==0`` 的read立即返回0，即EOF。
#. EOF是0-byte result，不会把用户buffer填零。
#. 本次read不进入wait queue，也不发生scheduler切换。
#. 返回EOF不会关闭read fd，也不会释放pipe object。
#. stream endpoint没有普通文件position语义。

资料
----

* `Linux 7.2-rc1 fs/read_write.c：ksys_read、vfs_read与stream ppos选择 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/read_write.c>`_
* `Linux 7.2-rc1 fs/pipe.c：anon_pipe_read与empty/writers判断 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pipe.c>`_
* `Linux 7.2-rc1 include/linux/pipe_fs_i.h：pipe ring与empty定义 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/pipe_fs_i.h>`_
