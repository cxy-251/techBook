第167章：Module Parameters 与驱动专用调优
=========================================

核心知识点
----------

Module Parameter 是模块级策略输入
   参数把用户字符串转换成内核变量或回调输入，真正后果来自驱动何时读取该值以及怎样把它应用到队列、IRQ、DMA、Firmware 或硬件寄存器。

参数声明只定义入口
   ``module_param``、``module_param_named``、``module_param_array`` 与 ``module_param_cb`` 描述名称、类型、权限和处理方式；必须继续追踪变量引用与自定义 ``kernel_param_ops``。

类型转换不等于硬件校验
   通用框架可解析 ``bool``、整数、数组和字符串，但范围、依赖、设备能力及资源上限仍应由驱动验证。合法文本也可能对应非法硬件状态。

内建与可加载形态决定输入源
   ``=y`` 驱动通常从 Kernel Command Line 读取 ``module.parameter=value``；``=m`` 模块可由 ``modprobe``、``insmod`` 或 ``modprobe.d`` 提供参数。

加载时参数与运行时参数不同
   只在 Module Init 或 Probe 中读取的参数决定对象初始布局，之后修改变量不会自动重建已有设备。热路径读取或自定义回调才可能产生在线效果。

Sysfs 权限表达暴露方式
   ``/sys/module/<name>/parameters/<param>`` 投影模块变量。``0444`` 适合观察，``0644`` 允许进入写回调，权限位本身不证明在线重配置安全。

模块参数通常不是单设备配置
   一个模块可绑定多个设备，模块参数通常影响全部实例、未来实例或公共热路径。每设备控制更适合设备属性、Netlink、Devlink、EtHTool 等对象级接口。

在线重配置需要完整状态机
   可写参数若影响硬件，应先验证状态，阻止新工作，排空在途请求，同步 IRQ、NAPI、Worker 或 Timer，重配硬件，再恢复入口并报告失败。

参数文件值不等于实际设备状态
   新值可能只被后续 Probe 复制，也可能被裁剪或异步应用。验证应读取实际队列数、Feature、寄存器状态、错误计数和运行性能。

持久化依赖加载路径
   可加载模块通常使用 ``modprobe.d``；早期由 Initramfs 加载的模块还需把配置更新进 Initramfs。内建驱动则需修改正式 Boot Entry。

参数修改与卸载存在并发
   Sysfs 写回调、设备 Remove 和模块卸载必须共享生命周期协议。撤销参数文件只能阻止新入口，不能替代等待回调、异步工作和设备引用结束。

参数不是通用性能答案
   Ring、Queue、Timeout、Retry、Power 或 Offload 的适宜值取决于设备、Firmware 和负载。增大数值可能把丢包转换为内存占用、排队和更差尾延迟。

关键路径
--------

可加载模块参数：

::

   modprobe / insmod / modprobe.d 提供字符串
   → 参数框架匹配 module_param 元数据
   → 类型转换或自定义 Set Callback
   → 更新模块变量
   → Module Init / Probe / Open 读取
   → 构建设备与硬件状态

内建驱动参数：

::

   Kernel Command Line
   → module_name.parameter=value
   → 启动期通用参数解析
   → 内建 Driver Initcall / Probe
   → 参数复制到设备私有状态
   → 创建实际队列、Feature 与硬件模式

在线重配置：

::

   写 Sysfs Parameter
   → 权限与参数格式检查
   → 获取模块和设备生命周期保护
   → 验证新值及硬件能力
   → 停止新提交并排空在途工作
   → 更新软件与硬件状态
   → 恢复入口并发布实际结果

概念辨析
--------

* Module Parameter 与设备属性：前者通常属于模块全局策略；后者绑定具体设备或队列对象。
* 参数可写与在线可重配：Sysfs 文件可写只证明存在 Set Handler，不证明已有硬件状态能安全重建。
* 当前变量与实际状态：参数文件展示控制变量；设备可能保存 Probe 时的副本或经过能力裁剪后的结果。
* ``modprobe.d`` 与 Kernel Command Line：前者作用于用户态模块加载；后者作用于内建或启动期驱动。
* 增大限制与修复根因：更大 Queue、Timeout 或 Retry 可能延迟故障并放大资源占用，不能修复丢失完成或硬件卡死。

本章结论
--------

Module Parameter 是小型控制接口，不是硬件状态本身。只有明确输入来源、读取时机、对象作用域和重配置协议，参数修改才可被证明安全有效。