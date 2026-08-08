第175章：Open Ecosystem and Integrated Ecosystem
===============================================

核心知识点
----------

* Android 是多主体协作生态：AOSP 提供公共平台，Google 提供 GMS / Play 生态与兼容规则，OEM 负责产品化和系统策略，SoC Vendor 负责 BSP、driver、firmware、HAL 与硬件调校，运营商和区域政策还会继续改变最终行为。
* Apple 是垂直整合生态：硬件、OS、framework、开发工具、签名与 entitlement、系统服务、商店审核和更新渠道主要由 Apple 统一控制。
* Android 的开放性依赖显式兼容边界维持共同语义，例如 SDK、CDD / CTS、HAL、VINTF、vendor partition、GKI / KMI；这些机制保证接口形状，不保证所有设备体验完全一致。
* Apple 的一致性来自较少的硬件组合和集中控制链；第三方开发者主要在 public API、entitlement、sandbox、TCC 和分发政策允许的范围内扩展能力。
* Android 的优势是硬件形态、价格带、厂商创新和区域适配空间大；代价是测试矩阵、兼容判断、更新协同和设备差异更复杂。
* Apple 的优势是 API、硬件能力、系统更新和用户体验更容易统一；代价是底层定制和替换系统能力的空间更小。
* 比较两种生态时应看责任主体、接口边界、更新链、测试责任和失败表现，而不是用“开放”或“封闭”替代架构分析。

关键路径
--------

::

   Android:
   App → Public SDK → System Service → Permission / Policy
       → HAL / Vendor Implementation → Driver / Hardware
       ↘ GMS / OEM Service → User-visible Result

   Apple:
   App → Public Framework → Entitlement / TCC / Sandbox
       → System Daemon / Service → XNU / Driver Boundary → Hardware
       → Framework Callback / User-visible Result

分析同一 App 在两台设备上的差异时，先确认调用属于公共平台能力、Google / Apple 生态能力还是 OEM 扩展能力，再向下检查真实设备实现和策略。

概念辨析
--------

* ``AOSP`` 不等于 ``GMS``：AOSP 是 Android 开源平台基础，GMS 是 Google 授权的应用与服务集合。
* ``兼容`` 不等于 ``一致``：CTS / 接口稳定能约束最低行为，硬件能力、算法、后台策略和性能仍可不同。
* ``一体化`` 不等于没有分层：Apple 仍有 framework、daemon、XNU、driver、hardware 等层级，只是这些边界主要由同一平台方控制。
* ``开放生态`` 的核心不是 App 能绕过系统服务，而是更多厂商可以在受约束边界内实现设备和平台发行版。

本章结论
--------

Android 把平台交付拆给多方，以稳定接口换取硬件与生态多样性；Apple 把主要控制面集中在同一厂商，以垂直整合换取一致性和统一更新。判断平台差异时，应沿能力路径定位“谁定义接口、谁实现硬件、谁执行策略、谁负责更新”。