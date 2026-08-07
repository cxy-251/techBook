第010章：SoC Integration and Mobile Hardware Topology
======================================================

核心知识点
----------

* SoC topology 关注硬件 block 如何连接，而不只是有哪些 block。CPU cluster、GPU、NPU、ISP、video codec、display engine、modem、security block、sensor hub 与 memory controller 的连接关系决定真实数据路径。
* 多个高性能单元通常共享 DRAM、片上互连、cache hierarchy、IOMMU、功耗域和 thermal budget。单模块峰值性能不能独立解释整机负载。
* Camera frame、GPU texture、video frame、AI tensor 等都应按 ``producer → buffer → consumer`` 读取；buffer 所有权、格式转换和 fence 决定能否实现低拷贝数据流。
* Memory controller 是多媒体和 AI 的关键汇合点。相机、GPU、NPU、display、codec 同时工作时，memory bandwidth 可能比单元算力更早成为限制。
* I2C/SPI 多承担控制与状态，MIPI CSI/DSI、USB、PCIe、UFS、I2S 等承担高速或专用数据通路。控制面与数据面经常走不同硬件接口。
* Device tree、board description、firmware handshake 和 driver probe 用于建立内核可见的硬件地图；硬件被识别之后，才可能继续形成 HAL 与系统服务能力。
* Driver 负责把寄存器、队列、中断、DMA 和 power state 转成内核对象；HAL/daemon 再把厂商拓扑差异压缩成稳定平台接口。
* 拓扑会直接影响系统服务设计。共享 ISP、有限 overlay plane、单一 radio、共享音频 route 或有限 NPU queue 都要求服务层做并发仲裁和优先级管理。
* Zero-copy 是减少数据搬运的目标，不等于“完全没有内存操作”；它依赖共享 buffer、兼容格式、IOMMU 映射和正确同步。

关键路径
--------

相机预览叠加识别：

::

   camera sensor
   → camera interface
   → ISP
   → shared DRAM buffer
   → NPU inference
   → GPU overlay composition
   → display engine
   → panel

硬件发现：

::

   board / firmware description
   → kernel enumerates controller
   → driver probe
   → map MMIO / IRQ / DMA resources
   → firmware handshake
   → register kernel device
   → HAL / service exposes capability

Buffer 路径分析：

::

   identify producer
   → identify allocation owner
   → identify consumers
   → inspect copy / format conversion
   → inspect fence / interrupt completion
   → inspect bandwidth and lifetime

概念辨析
--------

* **Component map 与 topology**：component map 回答“有什么”，topology 回答“怎么连接、共享什么、数据怎么走”。
* **控制总线与数据总线**：sensor 的曝光参数可能经 I2C 下发，而图像主体经 MIPI CSI 高速传输；两条路径职责不同。
* **硬件发现与能力开放**：driver 成功 probe 只说明内核识别设备，App 是否可用还要经过 HAL、service、permission 和 policy。
* **Zero-copy 与无同步**：共享同一 buffer 能减少复制，但 producer/consumer 仍必须通过 fence、引用计数或队列协调生命周期。
* **共享资源与独立模块**：两个硬件单元逻辑上独立，也可能共享 DRAM、power domain 或 thermal budget，因此会互相影响性能。

本章结论
--------

SoC 拓扑决定数据如何在硬件之间移动，也决定哪些资源必须由系统统一仲裁。理解移动硬件不能停在 CPU/GPU/NPU 名词表，而要继续追踪互连、DRAM、DMA、外设控制器、设备发现、buffer ownership 和同步关系；这些共享点才是很多性能、功耗和兼容性问题的真实边界。