第054章：Filesystem and OS Abstraction
======================================

核心知识点
----------

* Python 离开纯对象计算后，常见边界链是 ``Path → file object → file descriptor → filesystem / process``；不同层承担不同责任。
* ``pathlib`` 负责路径对象语义。PurePath 只做 lexical 路径计算；具体 ``Path`` 在调用 ``open``、``mkdir``、``stat``、``resolve`` 等方法时才进入真实文件系统。
* 创建 ``Path`` 不等于检查文件存在，也不等于解析符号链接；路径表达和 filesystem state 必须分开。
* ``os.fspath()`` / ``__fspath__`` 是 PathLike 协议边界，让 ``Path`` 能进入 ``open``、``os``、``subprocess`` 等底层接口。
* ``os`` 更接近 OS 接口：环境变量、工作目录、路径命名空间、权限、fd、rename/replace、进程级状态等都通过它进入系统边界。
* Python text file object 在 fd 之上叠加编码和缓冲；``write``、``flush``、``fsync`` 分别处在不同持久化层级。
* ``file.fileno()`` 暴露底层 fd；fd 是 OS 资源标识，不等于 Python file object 本身。
* ``os.replace(temp, target)`` 常用于同一 filesystem 上的原子名字替换；“临时文件完整写入 + fsync + replace”比直接覆盖目标更容易维持可见一致性。
* ``sys`` 暴露当前 Python interpreter 的启动与运行状态，如 ``sys.argv``、``sys.path``、``sys.executable``、标准流、模块表和 hook。
* ``sys.path`` 是 import system 的搜索路径，不等于当前工作目录；启动方式、虚拟环境、``PYTHONPATH``、``site`` 初始化都会影响它。
* ``sys.argv`` 是解释器已经解码后的参数列表；需要底层文件系统字节表示时可结合 ``os.fsencode`` / ``os.fsdecode``。
* ``subprocess`` 创建新的 process boundary：子进程有自己的地址空间和解释器/程序状态，父进程通过 argv、env、cwd、stdin/stdout/stderr 与 exit code 控制交互。
* ``subprocess.run`` 返回 ``CompletedProcess``；``returncode``、``stdout``、``stderr`` 是判断外部命令是否成功的核心证据。
* ``env=`` 会显式定义子进程环境；传入独立 env 时应基于 ``os.environ`` 复制/合并，否则可能无意丢失 PATH 等关键变量。
* ``text=True`` 在 pipe 上增加文本编码层；binary mode 则直接传 bytes。编码问题要先确认边界在哪一侧完成转换。
* ``cwd`` 只改变子进程工作目录，不等于修改父进程 ``os.getcwd()``。
* 文件、进程、标准流和 fd 都是显式资源，生命周期应通过 ``with``、``Popen`` context manager、``communicate``、``wait`` 等路径闭合。

关键路径
--------

文件写入与替换：

::

   Path target
       ↓
   create temp Path
       ↓
   open text file
       ↓
   encode + buffered write
       ↓
   file.flush()
       ↓
   os.fsync(file.fileno())
       ↓
   close file
       ↓
   os.replace(temp, target)
       ↓
   target name points to new file

子进程调用：

::

   parent interpreter
       ↓
   build argv / cwd / env
       ↓
   subprocess.run / Popen
       ↓
   OS creates child process
       ↓
   child receives environment + stdio
       ↓
   child executes program
       ↓
   exit code + stdout/stderr
       ↓
   parent interprets CompletedProcess

路径到 OS：

::

   PathLike object
       ↓
   os.fspath / implicit PathLike protocol
       ↓
   str or bytes filesystem path
       ↓
   OS API / file open / process cwd

概念辨析
--------

* **路径对象与文件**：``Path`` 是位置表达；真实文件是否存在、权限如何，要由 filesystem operation 确认。
* **lexical path 与 resolved path**：``parent``、``suffix``、``parts`` 属于文本结构；``resolve`` 会结合 cwd、符号链接和真实文件系统。
* **file object 与 fd**：file object 管理 Python 缓冲/编码和关闭协议；fd 是内核级资源句柄。
* **``flush`` 与 ``fsync``**：flush 处理 Python 缓冲，fsync 请求内核同步对应 fd；二者覆盖层级不同。
* **``sys`` 与 ``os``**：``sys`` 主要暴露解释器状态；``os`` 主要暴露进程和操作系统接口。
* **``sys.path`` 与 ``PATH``**：前者用于 Python import，后者是 OS 查找可执行程序的环境变量。
* **父进程与子进程状态**：子进程继承或接收快照式 argv/env/cwd/stdio，之后两边的普通 Python 对象并不共享。
* **stdout 文本与 bytes**：是否自动编码/解码取决于 ``text``、``encoding`` 和流包装层。

本章结论
--------

Filesystem and OS abstraction 可以压缩为“路径先表达位置，file object 管理 Python I/O 语义，fd 连接内核资源，subprocess 建立新的进程边界，sys 暴露当前解释器状态”。排查问题时先定位现象属于哪一层，再看对应证据：Path 的 lexical 结果、文件缓冲/fd、OS 权限和 replace、sys.argv/sys.path，或子进程 returncode/stdout/stderr。层级定位正确，绝大多数文件与进程问题都能沿同一条边界链解释。