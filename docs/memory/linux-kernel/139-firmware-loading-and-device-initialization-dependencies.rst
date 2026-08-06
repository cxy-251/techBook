第139章：固件加载与设备初始化依赖
==================================

本章必须记住
------------

#. 驱动匹配成功只说明设备被发现并找到候选驱动，不表示设备内部控制器已经具备工作能力。
#. 某些设备必须在 ``probe``、resume 或 reset 后加载外部 firmware，才能启动微控制器、DSP、GPU、网卡、触控或协处理器。
#. Firmware loader 负责把 blob 交给驱动，不理解设备私有格式、寄存器协议、签名、分段和启动流程。
#. ``request_firmware()`` 的稳定输入是固件名和 ``struct device``，输出是 ``struct firmware`` 或负错误码。
#. ``struct firmware`` 主要提供 ``data`` 和 ``size``；驱动必须自行验证长度、版本、校验、签名和兼容性。
#. 同步 ``request_firmware()`` 可能睡眠，不能在硬中断、原子上下文或持 spinlock 路径调用。
#. 典型加载顺序是：准备电源/时钟/reset → 请求 blob → 校验 → 上传设备 → 等待 ready → 释放内核侧 firmware 对象 → 发布上层功能。
#. ``release_firmware()`` 只释放内核持有的 blob 资源，不会让设备内部已经运行的 firmware 停止。
#. 固件请求成功只说明内核找到了字节序列，不说明设备已经接受、校验或运行它。
#. 固件文件缺失、文件读取失败、blob 校验失败、上传失败和设备 ready 超时属于不同故障阶段。
#. ``request_firmware()`` 返回 ``-ENOENT`` 常指向固件名、安装路径、initramfs 或 loader 策略问题。
#. 找到文件后设备无响应，通常要转向驱动上传顺序、版本兼容、电源、reset、MMIO、DMA 和内部状态机。
#. 固件名可能是固定字符串，也可能由设备 ID、revision、DMI、ACPI、Device Tree 或模块参数派生。
#. 诊断时必须记录驱动最终请求的完整文件名，不能只按设备商品名猜测。
#. 同一硬件 revision 可能要求不同 blob；错误版本可能加载成功却在运行期暴露隐蔽故障。
#. 固件版本协商应在上层接口开放前完成，避免用户请求进入半初始化设备。
#. ``request_firmware_nowait()`` 把取得结果改为异步回调，不能省略设备对象、回调对象和 remove 竞态管理。
#. 异步回调执行时设备可能已被移除、unbind、suspend 或 reset，必须持有正确生命周期并检查状态。
#. 异步请求的 ``fw == NULL`` 或错误结果也需要完整失败路径，不能假设回调只在成功时运行。
#. ``firmware_request_nowarn()``、``request_firmware_direct()``、``request_firmware_into_buf()`` 等变体表达不同告警、fallback 和缓冲策略，具体可用性具有版本差异。
#. 必需固件缺失通常应使 probe 失败；可选固件可以降级功能，但必须明确对用户可见的能力差异。
#. ``dev_err_probe()`` 可统一记录和传播 probe 错误，但不能把永久缺失固件误报为 ``-EPROBE_DEFER``。
#. ``-EPROBE_DEFER`` 适合 supplier 尚未准备好；普通固件文件暂时不存在是否可 defer 要按实际初始化依赖设计。
#. 直接文件系统查找、内建 firmware、缓存和可选用户态 fallback 都属于 loader 路径，实际启用情况取决于配置和发行版策略。
#. Firmware fallback 可能通过 sysfs/uevent 请求用户态提供 blob，会引入额外等待和超时。
#. 不能假设所有发行版都启用相同 fallback，也不能依赖未文档化的用户 helper 行为。
#. 早期启动设备可能在真实 root filesystem 可见前请求 firmware。
#. 此时固件通常需要放入 initramfs、编入内核，或由平台固件提供。
#. 根文件系统依赖某存储或网络设备时，该设备 firmware 未进入 initramfs 会形成启动循环依赖。
#. Built-in firmware 可在极早期可用，但会增加内核镜像、构建和许可证维护成本。
#. Initramfs 中有文件不等于最终 root filesystem 中也存在；resume、unbind/rebind 或后续 reset 可能再次请求固件。
#. 休眠恢复时，驱动或设备可能需要在普通用户态完全恢复前再次取得 firmware。
#. Firmware cache 可帮助系统 suspend/hibernate 跨越文件系统不可用窗口，精确行为具有版本和配置边界。
#. 驱动不能默认设备在 suspend-to-RAM 后保留 firmware；硬件电源域可能使内部控制器重启。
#. Resume 路径若需要重新加载 firmware，必须在重新开放队列、IRQ 和用户接口之前完成。
#. Runtime PM 低功耗是否丢失 firmware 状态取决于设备具体电源状态，不能沿用 system suspend 假设。
#. Firmware 上传可能使用 MMIO、PIO、DMA、mailbox 或总线专用传输，必须遵守各自同步和完成规则。
#. 使用 DMA 上传时，buffer 映射、方向、cache 可见性和设备完成仍适用普通 DMA 生命周期。
#. 上传结束后立即释放临时 DMA buffer 前，必须确认设备已经不再读取该内存。
#. Firmware blob 来自用户空间文件系统，不应直接信任内部长度、offset、计数和表项。
#. 解析时必须检查整数溢出、范围、对齐、重复项、压缩长度和所有偏移是否落在 blob 内。
#. 设备签名验证、Secure Boot、平台信任链和驱动自身校验是不同层级。
#. Firmware 文件的许可证、再分发权限和安装位置属于发行版与供应链约束，不由内核 API 自动解决。
#. 驱动中的 ``MODULE_FIRMWARE()`` 可声明模块可能需要的固件名，帮助打包工具收集依赖。
#. ``MODULE_FIRMWARE()`` 是元数据，不会自动把文件下载、安装或上传给设备。
#. 动态生成的固件名、条件分支和平台特定文件可能难以被静态打包工具完整发现。
#. 固件缺失日志应包含设备身份、文件名和错误码，避免只打印“firmware failed”。
#. 固件上传失败日志应区分校验失败、传输失败、设备拒绝、ready timeout 和版本不兼容。
#. 反复自动重试缺失固件会拖慢启动并制造日志风暴，应设置有界策略。
#. 设备 reset 后旧 firmware session、队列 token、feature negotiation 和校准状态可能全部失效。
#. 驱动必须把 firmware 生命周期与硬件 generation 绑定，避免迟到 completion 命中重启后的新会话。
#. 多功能设备可能由一个功能负责加载公共 firmware，其他功能必须通过设备链接或共享核心协调。
#. 多个驱动同时上传同一控制器会破坏设备状态，应建立单一 owner 和序列化协议。
#. Hotplug remove 期间必须取消或等待 firmware 请求和上传工作，再释放 MMIO、DMA 和私有对象。
#. Driver unbind/rebind 后是否重新加载 firmware 取决于设备是否 reset 和内部状态是否保留。
#. 用户手工替换固件文件不会自动更新正在运行的设备，通常需要 reset、unbind/rebind 或重启。
#. 滚动更新固件前应考虑旧内核驱动与新 firmware、以及新驱动与旧 firmware 的兼容矩阵。
#. Firmware 不是内核 UAPI，但文件名和行为可能成为系统部署合同，修改时需要兼容与回退策略。
#. ``dmesg``、``modinfo``、initramfs 内容和目标根文件系统固件目录是基础证据。
#. ``strace`` 用户程序通常看不到内核内部同步请求全过程，不能替代内核日志和 loader trace。
#. Ftrace/function graph 可观察 loader、probe 和上传路径，但 blob 内容与设备协议仍需驱动日志或硬件 trace。
#. 诊断早期启动缺失时，应检查 initramfs 是否包含最终请求名，而不是只检查运行系统 ``/lib/firmware``。
#. 诊断仅 resume 后失败时，应检查 firmware 是否丢失、缓存是否可用、文件系统是否已恢复以及重载顺序。
#. 诊断仅特定硬件 revision 失败时，应检查名称选择、版本表、校准数据和设备 ID 分支。
#. 精确固件查找路径、fallback 策略、缓存和 API 变体属于内核配置与版本敏感实现。
#. 稳定源码阅读顺序是：probe/resume 入口 → firmware 名生成 → loader 请求 → blob 校验 → 上传协议 → ready 状态 → 上层接口发布 → remove/reload。

必背路径
--------

Probe 中加载 Firmware：

::

   总线匹配设备与驱动
   → probe 准备 power / clock / reset / MMIO
   → request_firmware(name, dev)
   → loader 查 built-in / filesystem / fallback
   → 返回 struct firmware
   → 驱动验证 size、version、format
   → 上传设备并启动内部控制器
   → 等待 ready / handshake
   → release_firmware
   → 注册上层队列和用户接口

早期启动依赖：

::

   启动设备驱动在 rootfs 前 probe
   → 请求 firmware
   → 从 built-in 或 initramfs 查找
   → 上传设备
   → 存储/网络设备可用
   → 挂载真实 root filesystem
   → 后续系统继续启动

异步 Firmware 请求：

::

   持有设备与私有对象生命周期
   → request_firmware_nowait
   → probe 进入等待/降级状态
   → loader 回调返回 fw 或失败
   → 检查 removing / generation
   → 校验并上传
   → 成功后发布功能
   → 失败时撤销部分初始化
   → 释放 firmware 与对象引用

Resume 重载：

::

   恢复电源与总线访问
   → 判断内部 firmware 是否保留
   → 必要时取得缓存/blob
   → reset 内部控制器
   → 上传与握手
   → 恢复 DMA ring、IRQ 和会话
   → 最后开放上层请求

必须区分
--------

* 设备枚举与设备可用：枚举创建硬件对象；firmware 可能仍是进入工作态的必需依赖。
* Loader 成功与设备启动成功：Loader 只提供字节；驱动上传和设备 ready 才完成初始化。
* 固件文件缺失与固件不兼容：前者失败在查找；后者可能成功读取后在校验或运行阶段失败。
* Initramfs 文件与 Rootfs 文件：两个文件树服务不同启动阶段，必须分别确认。
* ``MODULE_FIRMWARE`` 与实际加载：元数据帮助打包；请求、校验和上传仍由驱动执行。

一句话结论
----------

Firmware 是许多现代设备从“已发现”到“可工作”的关键依赖，文件查找、blob 生命周期、硬件上传、版本兼容和电源恢复必须组成一条完整初始化协议。
