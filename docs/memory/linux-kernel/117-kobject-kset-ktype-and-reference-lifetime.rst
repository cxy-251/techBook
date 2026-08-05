第117章：kobject、kset、ktype 与引用生命周期
============================================

本章必须记住
------------

#. ``kobject`` 提供内核对象的名称、父子层级、集合归属、sysfs 表示和基础引用计数，不保存具体业务状态。
#. 真实内核对象通常把 ``struct kobject`` 嵌入更大的宿主结构体中，而不是单独动态使用一个裸 kobject。
#. 宿主结构体保存设备、驱动或子系统私有状态；kobject 只提供通用对象基础设施。
#. ``container_of()`` 把通用 ``struct kobject *`` 转回宿主结构体，是属性回调和 release 路径的关键。
#. 一个宿主对象应有清晰的主生命周期和最终释放者，不能让多个独立 kobject 引用计数竞争释放同一块宿主内存。
#. ``kobject_init()`` 初始化 kobject 并建立初始引用，但不自动把对象加入 sysfs 层级。
#. ``kobject_add()`` 设置名称和父关系并把对象加入层级；``kobject_init_and_add()`` 组合两步。
#. 一旦调用初始化或添加接口，失败清理也应遵循 ``kobject_put()`` 路径，不能直接 ``kfree`` 宿主对象。
#. ``kobject_get()`` 增加引用，``kobject_put()`` 减少引用；最后一个引用释放时进入 ``ktype->release()``。
#. ``kobject_put()`` 返回后对象可能已经被释放，调用者不能继续解引用原指针。
#. 引用计数只保证对象内存生命周期，不自动保证宿主内部状态的一致性和硬件可用性。
#. Sysfs 访问可以让对象内存保持有效，但属性回调仍要检查对象是否 online、dying、removed 或 suspended。
#. ``struct kobj_type`` 定义某一类 kobject 的释放回调、sysfs 操作和默认属性组。
#. ``ktype->release()`` 是宿主对象最终内存释放的唯一可靠落点之一，必须能够从 kobject 恢复宿主对象。
#. 缺失 release 回调会导致对象无法正确释放并产生告警或泄漏。
#. Release 回调执行时，业务对象应已经停止外部可见性和异步访问；release 不适合作为第一次停止硬件的地方。
#. ``release()`` 负责最后存储释放，不替代 remove、cancel work、free IRQ、停止 DMA 等前置 teardown。
#. ``struct kset`` 是 kobject 集合，同时自身也嵌入一个 kobject，因此集合可以作为 sysfs 目录和父节点。
#. 成员对象通过 ``kobj->kset`` 归属集合，kset 可以影响默认父节点、成员列表和 uevent 上下文。
#. Kset 组织对象，不自动接管每个成员宿主结构体的业务资源和最终 release。
#. ``kset_register()`` 通常初始化并加入集合对象；``kset_unregister()`` 撤销可见性并释放对应引用。
#. Kset 的成员仍需分别结束各自生命周期；先销毁集合前必须确保成员关系和引用处理符合实现要求。
#. ``kset_uevent_ops`` 可以过滤事件、设置 subsystem 名或添加环境变量，影响用户空间看到的 uevent。
#. Kset 的事件上下文与 ktype 的释放职责不同，不能混为一个对象类型机制。
#. Kobject 的 ``parent`` 决定对象层级；显式 parent 和 kset 默认 parent 的关系必须在加入前确定。
#. 对象加入后再随意改变 parent、name 或 kset 会破坏 sysfs 路径、链接和并发访问假设。
#. 对象名是 sysfs ABI 的一部分；发布后重命名可能影响用户空间，必须使用受支持接口并评估兼容性。
#. ``kobject_set_name()`` 等接口负责安全格式化名称，不能把临时栈字符串的生命周期错误地挂给对象。
#. Kobject 状态位用于记录是否初始化、是否已加入、是否发送过 add/remove uevent 等内部阶段，具体字段属于版本细节。
#. 调用者不能绕过公共接口直接修改 kobject 内部引用计数、sysfs 目录项或状态位。
#. Sysfs 目录创建成功后，用户空间可以并发打开属性、解析链接和触发回调；创建者必须假设对象已被外部观察。
#. Add uevent 应在对象必要属性和关系已建立后发送，避免用户空间收到事件却读到半初始化状态。
#. Remove uevent 和 sysfs 删除只停止新可见入口，不保证旧属性访问或其它引用瞬间结束。
#. 删除 sysfs 文件前应先阻止新业务操作，再等待或允许已有操作在安全状态下完成。
#. ``sysfs_create_group()``、默认 groups 和 ktype groups 都只组织属性可见性，不代替业务字段同步。
#. Attribute 的 show/store 回调必须把 kobject 恢复到正确宿主类型，错误的 ``container_of`` 类型会形成严重内存破坏。
#. Show/store 中不能假设对象一定绑定驱动或硬件在线，应根据生命周期状态返回适当错误。
#. Sysfs store 可能睡眠，应遵守对应属性和对象锁规则；不能在不允许睡眠的上下文直接复用该路径。
#. 引用获取与对象查找必须配对，任何成功 ``kobject_get()`` 都应有明确 ``kobject_put()`` 所有者。
#. 在链表、哈希表或全局索引中发布对象时，索引查找和 kobject 引用取得需要同一个并发协议。
#. 只从索引取出裸指针、随后再无保护地 get 引用，可能与并发删除形成 UAF。
#. 安全查找通常要在锁、RCU 或其它保护下确认对象仍可取得引用，再离开查找保护。
#. Kobject 引用计数不自动防止 ABA：同一地址释放后可能被新对象复用，外部 token 需要 generation 或独立身份验证。
#. 父对象关系通常隐含对象层级引用，但精确持有关系应按当前 kobject/device API 阅读，不能自行假设所有 parent 都被永久 pin。
#. 子对象未销毁前释放父宿主会破坏 sysfs 层级和回调，teardown 必须按子对象到父对象顺序收束。
#. 对象从 sysfs 消失不代表 release 已执行；残余引用会让宿主内存继续存在。
#. 对象仍在 sysfs 中也不代表业务设备正常；属性可以展示错误、离线或解绑状态。
#. 引用泄漏表现为 release 长期不执行、sysfs 残留、模块无法卸载或对象计数持续增长。
#. 提前 put 或缺少 get 会表现为 sysfs 访问、work、timer 或异步回调中的 use-after-free。
#. Double put 会导致引用提前归零；缺少 put 会导致永久泄漏，两者都应追踪每个引用的所有权转移。
#. ``kref`` 与 kobject 的关系是基础引用机制与对象基础设施关系；调用者通常应使用 kobject API 而不是直接操作内嵌 kref。
#. Device 对象已经包装了 kobject 生命周期时，应使用 ``get_device()/put_device()``，不要混用裸 ``kobject_get/put`` 破坏抽象层。
#. Driver、class、module 等对象也可能使用 kobject/kset 基础设施，但各自有更高层注册和释放 API，应优先使用高层接口。
#. 高层 API 可能额外维护 bus 列表、sysfs 链接、模块引用和 PM 状态，裸 kobject API 无法替代。
#. Kobject 的 release 可能在最后一次 put 的任意上下文发生；释放逻辑必须遵守该 API 对上下文的约束，不能无条件执行可能不安全的操作。
#. 若最终释放需要复杂、可睡眠或分阶段 teardown，应在上层 remove 阶段完成，release 只做最终资源归还。
#. 调试时应记录对象分配、init/add、每次 get/put、sysfs add/remove、uevent 和 release 的时间顺序。
#. Dynamic debug、tracepoint、KASAN、kmemleak 和 refcount 调试可以协助定位生命周期错误，具体可用事件依版本而异。
#. ``/sys/kernel/debug/kobject`` 一类调试入口并非稳定通用接口，不能假设所有内核都存在。
#. 稳定分析顺序是：宿主结构体 → 内嵌 kobject → ktype → parent/kset → 发布点 → 引用取得点 → remove → 最后 release。
#. 稳定模型是“kobject 管理可见性和引用终点”；精确内部字段、sysfs 实现和 uevent 时序属于版本敏感细节。

必背路径
--------

创建嵌入式 kobject：

::

   分配宿主对象
   → 初始化业务锁和状态
   → kobject_init 指定 ktype
   → 设置 kset/parent
   → kobject_add 设置名称并加入层级
   → 创建属性组
   → 发送 add uevent
   → 对外发布宿主对象

取得与释放引用：

::

   在锁/RCU/索引保护下查到对象
   → 确认对象仍允许取得引用
   → kobject_get 或高层 get_device
   → 离开查找保护
   → 使用对象并检查业务状态
   → kobject_put 或 put_device
   → 最后引用触发 release

最终销毁：

::

   标记对象 dying
   → 从查找结构摘除
   → 删除属性和外部入口
   → 发送 remove uevent
   → 等待 work、timer、IRQ、RCU 和普通引用
   → kobject_put 创建者引用
   → kref 归零
   → ktype->release
   → container_of 找回宿主对象
   → 释放宿主内存

Kset 组织成员：

::

   创建并注册 kset
   → 成员对象设置 kobj.kset
   → 设置显式 parent 或使用 kset kobject
   → 添加成员 kobject
   → kset 影响 sysfs 目录与 uevent
   → 分别删除所有成员
   → 结束成员引用
   → kset_unregister

诊断 release 不执行：

::

   确认对象已从 sysfs/索引删除
   → 确认创建者引用已 put
   → 检查 parent/child、open fd、work 和模块引用
   → 查找未配对 get_device/kobject_get
   → 检查 uevent/sysfs 回调是否仍持有对象
   → 观察最终 put 与 release

必须区分
--------

Kobject 与宿主业务对象
   Kobject 提供通用身份和引用；宿主结构体保存真正业务状态与资源。

Kset 与 Ktype
   Kset 组织对象集合和事件语境；ktype 定义对象类型、属性操作和最终 release。

Sysfs 删除与对象释放
   删除目录阻止新可见访问；对象要等全部引用归零后才释放。

引用保护与状态保护
   引用保证内存仍在；锁和状态机保证字段、硬件和业务操作仍合法。

Remove 与 Release
   Remove 撤销功能并停止异步路径；release 在最后引用归零后释放宿主存储。

裸 Kobject API 与高层对象 API
   Device、driver、class 等对象应使用各自高层 get/put 和注册接口，以维护完整关系。

一句话结论
----------

``kobject`` 把内核对象的名称、层级、sysfs 可见性和引用终点绑在一起，安全销毁必须先结束业务可见性和并发使用，再由最后一次 put 进入 ``ktype->release()`` 释放宿主对象。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 24，Device Model, Kobject, Sysfs, Driver Core, and Device Lifetime；
* AIBook 章节：Chapter 117，kobject, kset, ktype, and Reference Lifetime；
* 源文件：``docs/LinuxK/Part_24_Device_Model_Kobject_Sysfs_Driver_Core_and_Device_Lifetime/Chapter_117_kobject_kset_ktype_and_Reference_Lifetime.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_24_Device_Model_Kobject_Sysfs_Driver_Core_and_Device_Lifetime/Chapter_117_kobject_kset_ktype_and_Reference_Lifetime.md>`_。