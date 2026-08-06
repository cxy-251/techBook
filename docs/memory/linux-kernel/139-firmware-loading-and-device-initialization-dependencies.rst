第139章：固件加载与设备初始化依赖
==================================

核心知识点
----------

Firmware 可能是设备可用性的必要组成
   驱动匹配和 probe 开始只说明内核认识设备；微控制器、DSP、GPU、网卡或协处理器常要加载 firmware 后才能建立真实数据面。

Firmware Loader 只交付字节
   ``request_firmware()`` 根据名称和 ``struct device`` 返回 ``struct firmware``。Loader 不理解设备格式、版本、签名、上传协议和 ready 状态。

加载成功与设备启动成功不同
   找到 blob 后，驱动仍要验证长度、版本、offset、校验或签名，再通过 MMIO、DMA、mailbox 或总线协议上传并等待设备确认。

同步请求受执行上下文约束
   ``request_firmware()`` 可以睡眠，不能在硬中断、原子上下文或持 spinlock 路径调用。Firmware 生命周期要覆盖完整解析和上传阶段。

异步请求扩大生命周期边界
   ``request_firmware_nowait()`` 返回后，设备可能先被 remove、suspend 或 reset。回调必须持有对象引用，并验证 removing 状态与硬件 generation。

Firmware Blob 属于不可信输入
   驱动要检查所有长度、计数、偏移、压缩范围和整数运算，不能因文件来自系统目录就直接信任内部结构。

早期启动依赖交付位置
   根文件系统可用前需要 firmware 的存储、网络或显示设备，必须从 built-in firmware 或 initramfs 获得 blob，否则会形成启动循环依赖。

Rootfs 与 Initramfs 是不同阶段
   运行系统中存在文件，不证明早期 probe 能找到它；反之 initramfs 中存在也不保证 resume、reset 或 rebind 时仍可再次加载。

电源状态可能丢失 Firmware
   Suspend、Runtime PM 或 reset 是否保留设备内部 firmware 取决于硬件电源域。需要重载时，必须先完成上传与握手，再恢复 ring、IRQ 和用户入口。

错误必须按阶段分类
   文件缺失、读取失败、格式不兼容、上传失败、设备拒绝和 ready timeout 属于不同故障，错误码与日志必须保留真实阶段。

关键路径
--------

Probe 中加载 Firmware：

::

   设备与驱动匹配
   → 准备 power、clock、reset 与 MMIO
   → request_firmware(name, dev)
   → loader 从 built-in / initramfs / filesystem 取得 blob
   → 驱动验证格式、版本与边界
   → 上传设备并启动内部控制器
   → 等待 ready / handshake
   → release_firmware
   → 发布上层功能

异步请求：

::

   取得设备和私有对象引用
   → request_firmware_nowait
   → 设备保持 waiting 状态
   → 回调收到 blob 或失败
   → 检查 removing 与 generation
   → 校验并上传
   → 成功后发布功能
   → 失败时撤销部分初始化
   → 释放 firmware 与对象引用

Resume 重载：

::

   恢复总线、电源与 MMIO
   → 判断内部 firmware 是否保留
   → 必要时取得缓存或重新请求 blob
   → reset 并上传 firmware
   → 完成握手与 feature negotiation
   → 重建 DMA ring、IRQ 和会话
   → 最后开放上层请求

概念辨析
--------

* 设备枚举与设备可用：枚举创建设备对象；firmware 可能仍是进入工作态的必要依赖。
* Loader 成功与硬件启动成功：Loader 只提供字节；驱动上传并收到 ready 才完成初始化。
* 文件缺失与版本不兼容：前者失败在查找；后者可能在校验、上传或运行阶段失败。
* Initramfs 与 Rootfs：两套文件树服务不同启动阶段，不能互相代替。
* ``MODULE_FIRMWARE`` 与实际加载：元数据帮助打包；请求、验证和上传仍由驱动执行。

本章结论
--------

Firmware 把许多现代设备从“已发现”推进到“可工作”；文件交付、blob 校验、硬件上传、对象生命周期、版本兼容和电源恢复必须组成同一条初始化协议。
