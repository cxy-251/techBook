第169章：procfs、sysfs 与 debugfs 控制面
=========================================

核心知识点
----------

虚拟文件只是统一入口
   procfs、sysfs 与 debugfs 都通过 VFS 暴露读写接口，但真实语义来自背后的内核对象、回调、作用域与生命周期，而不是路径看起来像文件。

procfs 主要投影进程和系统状态
   ``/proc/<pid>`` 通常关联 Task、MM、FD 与 Namespace，系统级节点可提供统计或控制。PID Namespace、Credential、Ptrace 规则和 LSM 会改变可见性。

``/proc/sys`` 属于 sysctl 控制面
   它虽然位于 procfs 树中，实际由 ``ctl_table`` 与 Handler 驱动，和普通 ``proc_ops`` 或 ``seq_file`` 节点不是同一协议。

sysfs 投影内核对象模型
   Device、Driver、Bus、Class、Block Queue 与 Module 通过 Kobject 层级形成目录和属性；属性作用域通常由所在对象目录决定。

规范对象路径比展示路径更重要
   ``/sys/class``、``/sys/bus`` 与 ``/sys/block`` 常是功能视图或符号链接，``/sys/devices`` 更接近对象主树。解释控制项前应解析实际宿主对象。

sysfs 属性通过 ``show``/``store`` 工作
   属性通常使用 ASCII 文本协议。``store`` 可以更新字段，也可以触发 Reset、Rescan、Unbind 或异步重配置，写入长度成功不代表动作完成。

debugfs 服务开发与内部诊断
   debugfs 可暴露寄存器、队列、Fault Injection、调试开关和复杂 Dump，通常不承诺稳定 ABI，也不适合成为生产业务依赖。

接口稳定性必须逐项分类
   文档化 Sysfs/Procfs ABI、管理员调优接口、Testing 接口与 Debugfs 私有节点具有不同兼容承诺。路径存在不能证明格式长期稳定。

控制文件分为状态值与命令触发器
   状态文件表达持续配置；Trigger 文件每次写入都可执行一次动作。写 ``1`` 后读回 ``0`` 可能表示动作已消费，而非写入失败。

作用域受 Mount 与 Namespace 影响
   Bind Mount 可改变可见路径，Mount Namespace 可隐藏或只读呈现控制树，但不会改变底层设备或全局对象本身的作用范围。

权限允许不等于操作安全
   Mode、Credential、Capability、User Namespace、LSM、Lockdown 与 Mount 状态共同决定入口权限；即使 Root 能写，仍必须满足设备状态机与业务依赖。

接口撤销与对象释放是不同边界
   删除 procfs、sysfs 或 debugfs 节点阻止新查找，已打开 fd、正在执行的回调、异步工作和硬件引用仍需单独同步后才能释放私有状态。

正式子系统接口优先
   Netlink、Ioctl、``ip``、``ethtool``、``tc``、``devlink``、``nvme`` 与 ``sysctl`` 往往提供对象身份、ExtAck 或事务语义，应优先于直接写未文档化节点。

关键路径
--------

识别控制接口：

::

   取得目标路径
   → 确认实际 Mount 与文件系统类型
   → 解析 Namespace 和规范对象路径
   → 定位 proc_ops / show-store / file_operations
   → 确认对象、作用域和 ABI 级别
   → 判断读写副作用与回滚方式

控制写入：

::

   用户写入文本或命令
   → VFS 与虚拟文件系统权限检查
   → 获取宿主对象生命周期保护
   → 回调解析输入并验证状态
   → 更新变量或触发下游动作
   → 通过对象状态、事件和日志验证结果

安全撤销：

::

   停止新控制请求
   → 删除或隐藏接口节点
   → 等待正在执行的回调
   → 停止异步工作与硬件访问
   → 释放对象引用和私有数据
   → 最终释放宿主对象

概念辨析
--------

* procfs 与 sysfs：procfs 主要投影进程和系统状态；sysfs 主要投影 Kobject/Device Model 对象及属性。
* sysfs 与 debugfs：sysfs 倾向文档化、对象级单值 ABI；debugfs 面向调试，格式和节点可随实现变化。
* Set Value 与 Command Trigger：前者保存持续状态，后者以一次写入触发一次动作。
* 文件写入成功与动作完成：回调接受请求不等于 Reset、Training、Scan 或异步配置已经结束。
* 接口删除与对象释放：撤销可见性只关闭新入口，旧 fd、回调和异步路径仍可能持有对象。

本章结论
--------

内核控制文件的语义由虚拟文件系统背后的对象和回调决定。先识别文件系统、对象作用域和 ABI 等级，再执行写入与生命周期操作。