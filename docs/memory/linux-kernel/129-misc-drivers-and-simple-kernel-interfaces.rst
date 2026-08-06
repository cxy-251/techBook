第129章：Misc 驱动与简单内核接口
================================

核心知识点
----------

Misc 只简化字符入口注册
   Misc framework 统一处理共享 major、minor 分配、字符设备查找和设备节点发布，减少样板代码；它不替代真实硬件驱动模型。

``miscdevice`` 不是完整设备对象
   ``struct miscdevice`` 主要保存名称、minor、``file_operations`` 和 parent。MMIO、IRQ、DMA、clock、PM 与热插拔通常仍由 PCI、USB 或 platform 父驱动管理。

动态 minor 不是稳定身份
   ``MISC_DYNAMIC_MINOR`` 适合大多数新设备。用户态应依赖节点名、父设备关系和正式 ABI，不能把运行期 minor 当作硬件序列号。

注册成功即发布接口
   ``misc_register()`` 返回成功后，用户态可能立即 open、ioctl 或 mmap。因此私有状态、锁、引用和 disconnected 状态必须预先初始化。

打开路径通常提供 miscdevice 指针
   Misc core 可把 ``file->private_data`` 初始设置为对应 ``miscdevice``。驱动随后恢复宿主对象，并为当前 fd 取得设备或会话引用。

Parent 连接入口与真实硬件
   ``parent`` 应指向承载该接口的真实 device，使 sysfs、PM、热插拔和诊断能追溯到正确总线对象。

适用范围由数据模型决定
   Misc 适合少量私有控制、短消息、管理节点或简单硬件通道。传感器、输入、视频、音频、网络和块存储应优先使用专业子系统。

简单注册不等于简单 UAPI
   ``read``、``write``、``poll``、``ioctl`` 和 ``mmap`` 仍承担完整文件 ABI。结构体版本、短传输、阻塞语义、错误码和兼容模式都需要长期稳定。

控制面不能绕过专业数据面
   Misc 可以作为标准子系统旁边的受控管理入口，但不能绕过其队列、格式、权限和资源仲裁规则直接操作硬件。

安全边界必须显式设计
   节点权限只限制谁能打开；敏感命令仍需 capability、LSM、参数范围、对象状态和调用者隔离检查，不能暴露任意物理地址或 DMA 内存。

Deregister 只关闭新入口
   ``misc_deregister()`` 阻止新的打开并撤销设备表示，不自动结束已有 fd、VMA、IRQ、work、DMA 或异步请求。

硬件 teardown 与会话释放应分离
   Remove 可以先让旧 fd 进入 disconnected 状态并停止硬件，再保留软件对象到最后引用归零，避免无限等待用户主动关闭句柄。

关键路径
--------

Misc 注册：

::

   父总线 probe 创建私有设备对象
   → 初始化硬件、锁、引用和状态机
   → 填充 miscdevice 的 name、minor、fops、parent
   → misc_register
   → misc core 建立 minor 映射和 device
   → uevent 触发 /dev 节点创建
   → 用户态可以立即 open

打开与访问：

::

   用户打开 misc 节点
   → 字符设备层按 minor 找到 miscdevice
   → 安装驱动 file_operations
   → 驱动从 private_data 恢复宿主对象
   → 取得设备或会话引用
   → read/write/poll/ioctl/mmap
   → release 归还引用

安全注销：

::

   设置 stopping/disconnected
   → 阻止新命令和硬件访问
   → misc_deregister 撤销新 open
   → 唤醒阻塞 read 与 poll
   → 停止 IRQ、DMA、timer、work 和异步请求
   → 旧 fd 返回断开错误
   → 等待 fd、VMA 和对象引用归零
   → 释放父设备资源与私有对象

概念辨析
--------

Misc 入口与真实设备模型
   Misc 提供字符节点；总线、资源、电源和热插拔仍由父设备及其驱动负责。

动态 minor 与稳定设备身份
   Minor 是运行期分发表键；稳定身份来自节点命名、parent、总线地址和 UAPI。

``misc_deregister`` 与最终释放
   Deregister 关闭新入口；旧 fd、VMA 和异步路径仍可延长对象寿命。

Misc 与专业子系统
   Misc 让驱动自定义文件 ABI；专业子系统提供标准对象、工具、权限和长期维护合同。

节点权限与接口安全
   文件模式控制打开权限；驱动仍须验证 capability、参数、地址和设备状态。

简单注册与简单生命周期
   Framework 只减少注册样板，不会自动解决 DMA、并发、热拔插和引用问题。

本章结论
--------

Misc framework 只集中简单字符入口的注册；驱动仍要为真实硬件、稳定 UAPI、安全边界、并发和移除后的旧 fd/VMA 建立完整生命周期。
