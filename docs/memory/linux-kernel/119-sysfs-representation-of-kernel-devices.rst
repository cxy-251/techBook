第119章：Sysfs 中的内核设备表示
===============================

核心知识点
----------

Sysfs 是对象关系投影
   它把 kobject、device、driver、bus、class 和 module 的当前关系映射成目录、属性和符号链接，不是磁盘配置文件树。

``/sys/devices`` 是主层级
   设备父子关系的 canonical path 通常位于 ``/sys/devices``。物理设备、逻辑子设备、接口和虚拟对象都可能进入这棵树。

Bus 与 class 提供交叉视图
   ``/sys/bus/<bus>/devices`` 按匹配域组织设备；``/sys/class/<class>`` 按用户功能组织对象。条目通常链接回同一 canonical device。

符号链接表达对象关系
   ``driver``、``subsystem``、``device`` 和 ``module`` 等链接分别表达绑定、子系统、功能依赖与代码来源。

同名路径不等于同一身份
   Eth 名称、sdX 名称和 class 名称都可能变化。诊断应保存 canonical path、PCI BDF、USB port path、dev_t、WWN 等稳定标识。

属性内容由回调动态生成
   ``struct attribute`` 描述名称和权限；device attribute 通过 ``show()`` 与 ``store()`` 读取或修改当前内核对象状态。

一个文件表达一个清晰属性
   Sysfs 倾向使用简洁 ASCII 接口。它不适合复杂命令协议、日志流或高带宽数据传输。

Store 是真实控制路径
   写属性可能触发 reset、unbind、remove、电源切换或队列重配置。回调必须严格解析、验证范围并检查设备状态。

基础引用不保证硬件可用
   Sysfs 核心可保护对象内存，但 show/store 仍要检查设备是否 online、removed、suspended 或 error。

Attribute group 管理可见性
   属性组把相关属性成组注册和撤销，减少部分创建失败状态。它不替代业务字段锁和生命周期同步。

Sysfs ABI 需要维护承诺
   稳定接口应在 ``Documentation/ABI`` 中记录。用户空间不应依赖未文档化目录细节或调试属性格式。

Sysfs 与 debugfs 分工不同
   Sysfs 表达设备模型属性和用户 ABI；debugfs 用于开发诊断，通常不保证长期兼容。

Uevent 与 sysfs 互补
   Uevent 通知对象发生变化，sysfs 提供变化后的关系和属性视图。事件接收者必须容忍对象继续变化或已经消失。

热插拔会制造遍历竞态
   解析链接、读取属性和遍历目录期间，对象可能 add、remove 或 rebind。脚本必须处理 ``ENOENT``、重试并重新验证身份。

目录存在不证明设备可用
   Device 可以存在但未绑定 driver；绑定成功后功能接口也可能因固件、PM、IRQ 或运行错误不可用。

目录消失不证明生命周期结束
   Sysfs 可见性撤销后，打开 fd、异步 work、父子引用和其它对象仍可让设备结构继续存活。

关键路径
--------

从 class 定位真实设备：

::

   /sys/class/<class>/<name>
   → 解析符号链接
   → 回到 /sys/devices canonical path
   → 沿 parent 确认拓扑
   → 检查 subsystem 确认 bus/class
   → 检查 driver 与 module
   → 读取必要属性和 uevent

读取属性：

::

   用户 read 属性文件
   → sysfs 定位 attribute
   → 调用 show 回调
   → 恢复宿主 device/kobject
   → 检查对象和硬件状态
   → 在适当同步下读取字段
   → 格式化文本并返回

写入属性：

::

   用户 write 属性文件
   → 权限与 LSM 检查
   → store 回调解析输入
   → 验证范围、状态和并发条件
   → 执行受控状态转换
   → 返回 count 或负 errno
   → 必要时发送 change uevent

概念辨析
--------

* ``/sys/devices`` 与 ``/sys/class``：前者展示 canonical 设备层级；后者提供功能交叉入口。
* Bus 视图与 Driver 视图：Bus 组织匹配域；driver 目录展示当前绑定实例。
* Sysfs 属性与普通文件：属性由内核回调即时生成或处理，不是持久化文件内容。
* 对象存活与硬件在线：引用保证内存；设备状态决定属性操作是否合法。
* Uevent 与 Sysfs：Uevent 通知变化；sysfs 提供变化后的可查询状态。
* Sysfs 与 Debugfs：Sysfs 面向对象 ABI；debugfs 面向版本敏感调试。

本章结论
--------

Sysfs 是 driver core 对象关系的实时投影；正确读法是从 bus 或 class 入口回到 ``/sys/devices`` canonical device，再沿 parent、driver、module 和属性还原设备状态。
