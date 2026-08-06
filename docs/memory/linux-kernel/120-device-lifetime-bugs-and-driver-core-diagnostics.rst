第120章：设备生命周期故障与 Driver Core 诊断
=============================================

核心知识点
----------

生命周期故障是多个时间线失配
   绑定状态、对象引用、硬件可用性、用户入口和异步执行必须按同一退出协议收束。任一层提前结束或长期不结束都会形成 UAF、泄漏或卡死。

Probe 失败面对半初始化对象
   每成功一步就新增一个回滚责任。资源、异步路径和外部接口必须按依赖关系记录，并在失败时逆序撤销。

Remove 面对已发布对象
   成功 probe 后，设备可能同时被 fd、sysfs、IRQ、DMA、timer、work、NAPI、PM 和上层子系统使用，因此 remove 不能只释放资源。

退出必须先关闭新入口
   Remove 的第一步是设置 dying、stopping 或 disconnected，并让 open、submit、ioctl、sysfs store 等入口拒绝新的业务操作。

外部接口先于底层资源撤销
   Netdev、cdev、gendisk、input 和 class 对象仍可触发驱动回调。必须先注销这些入口，再释放私有状态和硬件资源。

异步执行需要逐类同步
   IRQ、work、timer、tasklet、NAPI、线程和 RCU 各有独立同步接口。``synchronize_rcu()`` 不会等待 work、DMA、fd 或普通引用。

DMA teardown 具有严格顺序
   先停止新提交和硬件队列，再终止或等待在途传输，同步中断与 completion，最后 unmap 并释放 ring 和 buffer。

打开 fd 可以跨越物理移除
   Open 时必须取得覆盖 fd 生命周期的引用。Remove 撤销硬件能力并设置 disconnected，旧 fd 返回错误，最后 close 才归还对象引用。

对象引用与硬件状态必须分离
   Refcount 只保证内存存在。设备已经移除时，仍存活的对象只能提供安全错误语义，不能继续访问寄存器或提交 DMA。

Remove 与 release 是两个终点
   Remove 结束驱动主动能力；release 等待所有 fd、子对象和普通引用归零后释放宿主内存。复杂硬件停止不应拖到 release。

Managed resource 不覆盖全部清理
   Devres 可自动释放部分资源，但无法自动理解用户入口、协议队列、自重排 work、DMA 状态机和上层对象的注销顺序。

引用泄漏表现为终点不发生
   常见证据包括 release 长期不执行、模块无法卸载、设备对象残留，以及未配对的 get_device、module_get、open 或子对象引用。

Use-after-free 来自迟到访问
   常见来源是 remove 后的 IRQ、work、timer、sysfs、fd、PM 或 completion。修复应改变所有权和同步顺序，而不是增加固定 sleep。

Reset 与 remove 不能混用状态
   Reset 暂时停止并重建硬件；remove 永久撤销设备。旧 completion 需要 generation 或 epoch 防止命中新队列和新对象。

诊断必须使用稳定设备身份
   应记录 canonical DEVPATH、PCI BDF、USB path、dev_t 或 bus address，避免 eth0、sdX 等易变化名称造成错误关联。

证据必须覆盖完整生命周期
   最有价值的时间线是注册/发布、引用取得、异步启动、退出状态、入口撤销、同步等待、put 和最终 release。

关键路径
--------

Probe 失败回滚：

::

   分配私有对象与基础资源
   → 初始化 IRQ / DMA / work / queue
   → 某一步失败
   → 停止继续发布
   → 注销已发布接口
   → 停止并同步异步路径
   → 释放 DMA、IRQ、MMIO 和依赖
   → 清除 drvdata
   → 返回最初错误

成功设备 Remove：

::

   设置 dying / disconnected
   → 阻止新 open、submit 和控制写入
   → 注销 class 与上层接口
   → 停止 queue 和新 DMA
   → 屏蔽并同步 IRQ
   → cancel/flush work、timer、NAPI
   → 等待 RCU 与在途请求
   → 释放硬件资源
   → put 创建者引用
   → 最后引用归零后 release

诊断 UAF：

::

   保存 KASAN use 栈
   → 找到对象 alloc 与 free 栈
   → 确认释放发生在 unwind、remove 或 release
   → 找出迟到 IRQ/work/sysfs/fd/PM 路径
   → 检查缺失引用或同步
   → 修正入口关闭和等待顺序
   → 用热插拔与故障注入复测

诊断引用泄漏：

::

   确认 device_del/remove 已完成
   → 检查 release 是否执行
   → 枚举 get_device / kobject_get / module_get
   → 检查 open fd、子对象和 work 引用
   → 找到未配对 put
   → 验证引用归零和模块可卸载

概念辨析
--------

* Probe unwind 与 Remove：前者清理半初始化对象；后者撤销已发布并发对象。
* 对象引用与硬件可用性：引用保护内存；退出状态控制硬件访问。
* Remove 与 Release：Remove 停止能力；release 回收最终存储。
* RCU 与普通引用：RCU 等待旧读侧临界区；refcount 等待独立所有者归还引用。
* Cancel 与 Flush：Cancel 尝试阻止待执行工作并等待运行实例；flush 保证已排队工作完成，具体语义按对象类型判断。
* Fixed sleep 与同步证明：Sleep 只延迟竞态；completion、IRQ sync、flush、join 和引用归零才能证明执行结束。

本章结论
--------

设备 teardown 的稳定原则是先停止新访问，再排空所有旧访问，最后释放资源和对象；诊断必须沿发布、引用、异步执行、remove、put 与 release 的完整时间线定位失配点。
