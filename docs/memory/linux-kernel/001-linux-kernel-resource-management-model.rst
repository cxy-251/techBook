第001章：Linux 内核资源管理模型
===============================

本章必须记住
------------

#. Linux 内核负责管理 CPU、内存、文件、设备、网络和权限等系统资源。
#. 用户程序通常不能直接操作内核对象和硬件，而是通过系统调用请求内核服务。
#. 文件描述符 ``fd`` 是当前进程文件描述符表中的整数索引，不是文件本身。
#. 每个进程拥有自己的文件描述符表，因此不同进程中的同一个 ``fd`` 数值可以指向不同对象。
#. 文件描述符表中的条目引用 ``struct file``；``struct file`` 才是内核处理一次已打开文件实例时使用的对象。
#. ``struct file`` 保存打开标志、当前文件位置、关联对象以及操作表等运行时状态。
#. 多个文件描述符可以引用同一个 ``struct file``，此时它们可能共享文件位置和打开状态。
#. ``struct file`` 中的 ``file_operations`` 指针决定读、写、映射和轮询等操作进入哪个具体实现。
#. 同一个 ``read()`` 可以读取普通文件、管道、终端、设备或已连接的套接字，因为不同对象提供不同的读取实现。
#. 内核源码中的目录帮助定位代码，真正决定运行路径的是当前对象、对象状态和回调表。

必背路径
--------

::

   用户调用 read(fd, buf, count)
   → 进入系统调用
   → 在当前进程的文件描述符表中查找 fd
   → 取得 struct file
   → VFS 完成通用检查
   → 通过 file_operations 分派
   → 进入文件系统、管道、设备或其他具体实现

必须区分
--------

``fd`` 与 ``struct file``
   ``fd`` 是当前进程中的整数索引；``struct file`` 是内核中的打开文件对象。

``struct file`` 与 ``inode``
   ``struct file`` 表示一次打开产生的运行时对象；``inode`` 表示文件系统对象的元数据与身份。

系统调用入口与具体实现
   ``read()`` 提供统一入口；真正的数据来源和读取方式由对象的操作表决定。

一句话结论
----------

``fd`` 负责定位对象，``struct file`` 保存打开状态，``file_operations`` 决定具体行为。

来源
----

* AIBook 书籍：LinuxK；
* AIBook 章节：Chapter 1，Linux Kernel Resource Management Model；
* 源文件：``docs/LinuxK/Part_01_Kernel_Worldview_and_Engineering_Mental_Model/Chapter_001_Linux_Kernel_Resource_Management_Model.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_01_Kernel_Worldview_and_Engineering_Mental_Model/Chapter_001_Linux_Kernel_Resource_Management_Model.md>`_。
