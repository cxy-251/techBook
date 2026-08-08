第042章：Apple IOKit, DriverKit, and Controlled Driver Access
==============================================================

核心知识点
----------

* Apple 驱动体系的核心目标是让硬件可被系统识别和调用，同时把第三方驱动代码的权限、分发、崩溃和设备访问范围控制在明确边界内。
* IOKit 使用 ``IOService``、provider/client、matching、service object、I/O Registry 和 user client 组织设备与驱动关系。
* Device Matching 根据 provider class、设备属性、vendor/product id 等条件选择合适驱动；匹配成功后 driver/service object 接管设备并向上发布能力。
* ``IOService`` 生命周期围绕 init/start/stop/open/close/free 等责任展开，用于处理设备上线、client 访问、热插拔、电源状态和释放。
* User Client 是用户态访问 IOKit service 的受控桥梁。App 拿到的是允许调用的方法、memory mapping 或 data queue，而不是整个内核驱动对象。
* DriverKit 把部分第三方驱动从 kernel extension 移到独立用户态 Driver Extension 进程中，降低普通代码错误扩大为 kernel panic 的风险。
* User-space driver 并不意味着“直接硬件访问”。系统仍通过 provider/proxy、matching、entitlement、code signing、host process 和生命周期管理保留控制权。
* Driver Extension 属于受控系统扩展形态，通常随承载 App 分发，并通过系统激活流程、用户或管理员批准进入可用状态。
* Entitlement 与 code signing 把“谁有资格驱动哪类设备”绑定到签名身份和受控能力；设备存在不等于任意 App 或 extension 都能接管。
* Method dispatch、shared buffer、异步通知和 memory mapping 仍是高风险接口，需要严格检查 caller、selector、长度、ownership 和 lifetime。
* macOS、iPadOS、iOS 对第三方驱动开放程度不同。稳定判断应基于目标平台公开 DriverKit family、entitlement 和 framework，而不是假设 iOS 提供桌面级 raw driver access。

关键路径
--------

设备匹配：

::

   device appears
   → provider service published
   → matching dictionary evaluates properties
   → driver / Driver Extension selected
   → service object starts
   → user client or framework-visible capability published

DriverKit：

::

   hardware provider in system
   → system launches Driver Extension host
   → instantiate DriverKit IOService subclass
   → communicate through controlled proxy objects
   → client receives data / status

受控分发：

::

   signed host App + Driver Extension
   → required entitlement
   → activation request
   → system policy / user or admin approval
   → extension becomes active
   → matching and device access allowed

概念辨析
--------

* **IOKit 与 DriverKit**：IOKit 描述 Apple 驱动对象模型；DriverKit 把部分驱动实现迁移到用户态并保留受控匹配和 service 语义。
* **Service object 与 user client**：Service object 持有设备状态；user client 只暴露给特定用户态调用者的受控接口。
* **User-space driver 与 ordinary App**：DriverKit 进程仍属于特权受控组件，不等同于普通沙箱 App 可以任意访问设备。
* **Entitlement 与 runtime permission**：Entitlement 是签名时授予的特权能力，普通用户授权则是运行时资源许可，两者作用层级不同。
* **Device discovered 与 driver usable**：系统发现硬件只完成 provider 建立，后续仍需匹配、签名、entitlement、激活和 client authorization。

本章结论
--------

Apple 驱动模型强调“硬件可达必须转化为系统批准的能力可达”。IOKit 组织设备对象，DriverKit 改善故障隔离，entitlement、签名和激活流程控制第三方驱动边界。分析 Apple 外设问题时，应先看 provider/matching，再看 service/user client，最后看签名、entitlement 和平台开放范围。