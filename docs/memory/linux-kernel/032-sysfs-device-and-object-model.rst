第032章：sysfs 是设备与对象模型接口
===================================

本章必须记住
------------

#. ``sysfs`` 是通常挂载在 ``/sys`` 的伪文件系统，它把内核对象层级、设备模型关系和部分对象属性投影到用户空间。
#. sysfs 的中心对象不是进程，而是 ``kobject``、device、driver、bus、class 和 module 等内核对象。
#. 一个注册到内核对象体系中的 ``kobject`` 通常对应 sysfs 中的一个目录；父对象关系决定目录层级。
#. ``kobject`` 往往嵌入更具体的对象中，例如具体总线对象嵌入 ``struct device``，设备对象再使用 kobject 提供名称、层级、引用和 sysfs 表示。
#. ``/sys/devices`` 是设备对象的主树，表达设备在内核设备层级中的位置。
#. ``/sys/bus`` 按总线组织设备和驱动，适合观察设备枚举、驱动目录以及绑定关系。
#. ``/sys/class`` 按功能类别聚合设备，例如 ``net``、``block`` 和 ``tty``；其中条目通常是指向 ``/sys/devices`` 的符号链接。
#. ``/sys/module`` 暴露内建组件或可加载模块的参数、引用和部分状态。
#. sysfs 中的符号链接表示对象关系或另一种视图，不表示系统复制了一个新的设备对象。
#. 阅读 ``/sys/class/net/lo`` 时，应先用链接目标回到 ``/sys/devices/...``，再判断对象在设备树中的位置。
#. sysfs 普通文件通常表示对象属性，内核通过 ``show()`` 把对象状态格式化为文本，通过可选的 ``store()`` 接收用户写入。
#. sysfs 属性倾向于使用 ASCII 文本，并遵守“一文件一属性”的接口边界。
#. 属性权限只说明 VFS 读写权限；写入是否合法还取决于回调中的解析、范围检查、状态机、锁和安全策略。
#. 只读属性适合观察对象状态；可写属性可能改变 MTU、电源状态、驱动绑定、设备参数或其它运行行为。
#. ``bind``、``unbind``、``remove``、``rescan``、``power/control`` 等文件属于控制入口，写入可能导致设备停止、重新 probe 或改变电源管理状态。
#. 写入 sysfs 前必须确认目标对象、输入格式、当前状态和恢复方式，不能把它当成普通配置文件随意修改。
#. sysfs 目录存在通常说明对象已经注册并对外可见；目录消失通常表示对象被注销或当前视图不再暴露它。
#. 目录存在不保证设备硬件工作正常，也不保证驱动 probe 已完整成功；还要检查 ``driver`` 链接、状态属性和日志。
#. ``driver`` 符号链接可以说明对象当前绑定到哪个驱动；链接缺失可能来自未匹配、probe 失败、手动解绑或驱动未加载。
#. sysfs 属性回调运行时，宿主对象必须仍然存活；对象注销路径必须阻止新访问并等待正在执行的回调退出。
#. 删除 sysfs 文件只是关闭用户入口，不能代替停止 IRQ、workqueue、timer、DMA 和其它对象使用者。
#. sysfs 接口比 debugfs 更强调对象模型和用户态兼容性；已经形成用户态 ABI 的属性不能随意改名或改变语义。
#. 路径、目录和属性内容会受硬件、固件、驱动、内核配置、模块加载和权限影响。
#. 一个 sysfs 路径给出对象关系证据，不自动给出故障根因；应结合 ``/proc``、日志和 tracing 形成完整证据链。

必背路径
--------

从 sysfs 路径还原内核对象：

::

   判断路径位于 devices、bus、class 还是 module
   → 判断当前条目是目录、符号链接还是属性文件
   → 符号链接时追踪到 /sys/devices 中的目标目录
   → 确认对象的父子关系、总线、class 和 driver
   → 读取属性确认当前状态
   → 回到 struct device、kobject 和属性回调源码

设备与驱动绑定视图：

::

   /sys/devices 找设备主对象
   → /sys/bus/<bus>/devices 找总线设备入口
   → 查看设备目录中的 driver 链接
   → 进入 /sys/bus/<bus>/drivers/<driver>
   → 核对绑定设备链接
   → 结合 dmesg 判断 probe 成功或失败

属性读取路径：

::

   用户态 read 属性文件
   → kernfs 和 sysfs 定位 attribute
   → 调用对象类型对应的 show 回调
   → show 读取宿主对象状态
   → 格式化为文本
   → 返回用户空间

控制属性写入路径：

::

   保存修改前状态
   → 确认文件可写和输入格式
   → 用户态 write
   → 调用 store 回调
   → 解析并验证输入
   → 在锁和状态机约束下修改对象
   → 检查日志、属性和实际行为
   → 必要时恢复原状态

必须区分
--------

``/sys/devices`` 与 ``/sys/class``
   ``devices`` 表达设备主树；``class`` 提供按功能分类的视图，通常通过链接指向主对象。

设备对象与目录路径
   内核对象是运行时结构；sysfs 目录是它在用户空间的投影。

属性读取与属性写入
   读取通常观察状态；写入可能触发真实设备、驱动和电源状态变化。

目录存在与功能正常
   目录存在证明对象被发布到该视图；功能是否正常还要看绑定、probe、状态和 I/O 结果。

权限允许与操作安全
   文件权限允许写入不代表当前状态适合修改，store 回调和对象生命周期仍决定安全边界。

sysfs 与 debugfs
   sysfs 表达对象模型和较稳定属性；debugfs 表达开发调试状态，格式和语义通常不稳定。

一句话结论
----------

``sysfs`` 是内核设备与对象模型的用户态投影：目录表达对象，链接表达关系，属性表达状态，而可写属性会直接进入对象控制路径。

来源
----

* AIBook 书籍：LinuxK；
* AIBook 章节：Chapter 32，sysfs as a Device and Object Model Interface；
* 源文件：``docs/LinuxK/Part_07_Observability_Interfaces_procfs_sysfs_debugfs_tracefs_and_dmesg/Chapter_032_sysfs_as_a_Device_and_Object_Model_Interface.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_07_Observability_Interfaces_procfs_sysfs_debugfs_tracefs_and_dmesg/Chapter_032_sysfs_as_a_Device_and_Object_Model_Interface.md>`_。