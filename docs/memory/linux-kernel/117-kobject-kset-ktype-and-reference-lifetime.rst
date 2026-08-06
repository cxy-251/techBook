第117章：kobject、kset、ktype 与引用生命周期
============================================

核心知识点
----------

``kobject`` 是对象基础设施
   它提供名称、父子层级、集合归属、sysfs 表示和基础引用计数，不保存设备、驱动或子系统的主要业务状态。

Kobject 通常嵌入宿主对象
   真实对象把 ``struct kobject`` 嵌入更大的结构体中。属性回调和 release 使用 ``container_of()`` 回到正确宿主类型。

引用计数决定内存终点
   ``kobject_get()`` 增加引用，``kobject_put()`` 释放引用。最后一次 put 触发 ``ktype->release()``，其后原指针不可再使用。

``ktype`` 定义对象类型合同
   ``struct kobj_type`` 连接 release、sysfs 操作和默认属性组。Release 必须能够找到宿主对象并完成最终存储释放。

Release 不是 remove
   Remove 阶段应停止硬件、撤销入口并排空异步工作；release 只在所有引用消失后执行最终内存回收。

缺失 release 会破坏生命周期
   动态嵌入式 kobject 没有可靠 release 时，内核无法知道何时释放宿主对象，通常表现为告警或永久泄漏。

``kset`` 组织对象集合
   Kset 自身也含有 kobject，可形成 sysfs 目录，并为成员提供默认父节点、集合列表和 uevent 上下文。

Kset 不拥有全部业务资源
   成员加入 kset 不表示集合自动负责成员的 IRQ、work、设备状态或宿主内存。每个成员仍需自己的 teardown 与 release 协议。

Kset 与 Ktype 分工不同
   Kset 解决“对象属于哪个集合以及事件归属”；ktype 解决“对象是什么类型、有哪些属性、最后怎样释放”。

初始化与加入是两个阶段
   ``kobject_init()`` 建立类型和初始引用；``kobject_add()`` 设置名称、父关系并发布到层级。失败后也必须沿 put 路径清理。

发布意味着可并发访问
   对象加入 sysfs 后，用户空间可立即打开属性、解析链接和触发回调。必要字段、锁和状态必须在发布前完成初始化。

Sysfs 删除不等于对象释放
   删除目录和属性只阻止新的可见访问。旧引用、打开属性、父子关系或异步路径仍可让宿主对象继续存活。

引用保护不等于状态保护
   引用只保证内存未释放。对象是否 online、绑定、未移除，以及字段是否一致，仍需状态机、锁、RCU 或其它同步协议。

查找与引用提升必须原子协调
   从链表、哈希表或全局索引取得裸指针后再无保护地 get，可能与并发删除形成 UAF。查找保护内必须确认对象仍可取得引用。

父子销毁需要顺序
   子对象、属性和链接应先撤销，再释放父宿主。父内存过早释放会破坏 sysfs 层级及迟到回调。

高层对象应使用高层引用 API
   ``struct device`` 应使用 ``get_device()/put_device()``。高层 API 还维护 bus、模块、PM 与 sysfs 关系，不能与裸 kobject 引用任意混用。

关键路径
--------

嵌入式 kobject 创建：

::

   分配宿主对象
   → 初始化业务状态和锁
   → kobject_init 指定 ktype
   → 设置 kset 与 parent
   → kobject_add 设置名称并加入层级
   → 创建属性组
   → 发送 add uevent
   → 对外发布宿主对象

安全查找与使用：

::

   在锁或 RCU 保护下查找对象
   → 检查对象未进入 dying 状态
   → 取得 kobject 或高层对象引用
   → 离开查找保护
   → 在状态同步下使用对象
   → put 对应引用

最终销毁：

::

   标记对象 dying
   → 从索引和外部入口摘除
   → 删除 sysfs 属性与链接
   → 停止 work / timer / IRQ / RCU 使用
   → 释放创建者引用
   → 最后引用归零
   → ktype->release
   → container_of 找回宿主对象
   → 释放宿主内存

概念辨析
--------

* Kobject 与宿主对象：Kobject 提供通用身份和引用；宿主结构体保存真正的业务状态。
* Kset 与 Ktype：Kset 组织集合和事件语境；ktype 定义类型、属性和 release。
* Sysfs 删除与对象释放：删除可见入口；释放必须等待全部引用归零。
* Remove 与 Release：Remove 停止能力和并发；release 回收最终存储。
* 引用保护与状态同步：引用防止 UAF；锁和状态机保证操作仍合法。
* 裸 API 与高层 API：Device 等对象必须优先使用对应高层注册和 get/put 接口。

本章结论
--------

``kobject`` 把名称、层级、sysfs 可见性和引用终点连接起来；安全生命周期必须先撤销业务入口并排空并发使用，再由最后一次 put 进入 ``ktype->release()`` 释放宿主对象。
