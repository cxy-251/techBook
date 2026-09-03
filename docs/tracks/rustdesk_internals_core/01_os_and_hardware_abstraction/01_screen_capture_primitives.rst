======================================================================
01.01 跨平台屏幕像素捕获底层原语与抓屏引擎实现
======================================================================

.. note:: 前置背景与上下文承接
   远程桌面系统的性能天花板首先取决于**画面像素的采集效率与延迟**。在远程控制链路中，若每一帧的捕获需要消耗过多的 CPU 周期或发生冗余的显存-内存总线拷贝（PCIe DMA），将直接导致端到端延迟剧增并挤压后续视频编码器的计算资源。本章作为整部专著的技术基石，将深入解析 RustDesk 在 Windows、macOS 与 Linux 三大平台上所依赖的底层图形子系统捕获原语，并剖析其核心采集库 ``libs/scrap`` 的抽象机制。

***
图形合成器与显存帧缓冲物理模型
***

在现代多任务操作系统中，应用程序并不直接向物理显示器的帧缓冲区（Front Buffer / Back Buffer）写入像素，而是由**桌面窗口管理器 / 组合器（Compositor）**进行统一调度与渲染合成：

* **Windows**: 桌面窗口管理器（Desktop Window Manager, DWM）基于 Direct3D 表面管理各窗口图层。
* **macOS**: Quartz Compositor / WindowServer 维护基于 Metal/OpenGL 的 Surface 树。
* **Linux (Wayland)**: 组合器（如 Mutter、KWin、Sway）接管 KMS/DRM 页面翻转（Page Flip），各客户端通过共享内存或 DMA-BUF 提交缓冲区。

屏幕采集的物理本质，即是**以最小的性能惩罚介入合成流水线，获取最终合成帧或受监控窗口的像素矩阵**。

.. list-table:: 主流平台底层捕获 API 对比与性能特征
   :widths: 20 25 30 25
   :header-rows: 1

   * - 操作系统
     - 核心捕获 API
     - 内存路径 (Memory Path)
     - 硬件加速与零拷贝支持
   * - **Windows**
     - DXGI Desktop Duplication (DDA)
     - GPU VRAM $	o$ GPU Surface / PCIe DMA
     - 支持 Direct3D11 显存内直通编码
   * - **macOS**
     - Quartz / CGDisplayStream / ScreenCaptureKit
     - IOSurface / Shared Memory Frame
     - 结合 VideoToolbox 硬件编码
   * - **Linux (X11)**
     - X11 MIT-SHM / XGetImage
     - 共享内存段 (Shared Memory Segment)
     - 纯 CPU 内存拷贝，开销随分辨率增加
   * - **Linux (Wayland)**
     - PipeWire + XDG Desktop Portal
     - DMA-BUF / Memfd 共享文件描述符
     - 支持跨进程 DMA-BUF 零拷贝直通

---
Windows 平台：DXGI Desktop Duplication 机制
---

在 Windows 8 及更高版本中，传统的 GDI ``BitBlt`` 镜像驱动已被彻底弃用。RustDesk 在 Windows 端基于 **DirectX Graphics Infrastructure (DXGI) Desktop Duplication API (DDA)** 构建采集管线。

DDA 工作在 Direct3D 11 设备之上。其核心交互时序如下：

1. **初始化阶段**：枚举 ``IDXGIFactory1``，定位目标物理显示器对应的 ``IDXGIOutput1`` 接口。
2. **创建副本接口**：调用 ``IDXGIOutput1::DuplicateOutput``，传入 D3D11 Device 实例，获取 ``IDXGIOutputDuplication`` 对象。
3. **获取下一帧表面**：调用 ``IDXGIOutputDuplication::AcquireNextFrame``，设置超时时间。
4. **脏矩形与光标元数据提取**：解析 ``DXGI_OUTDUPL_FRAME_INFO``，提取变更区域（Dirty Rects）与硬件光标图形/位置信息。
5. **显存访问与释放**：映射桌面纹理资源，读取完成后立即调用 ``ReleaseFrame`` 归还缓冲控制权。

.. code-block:: rust
   :caption: Windows DXGI 捕获核心逻辑（基于 libs/scrap/src/dxgi/）

   pub struct DxgiCapturer {
       device: *mut ID3D11Device,
       context: *mut ID3D11DeviceContext,
       duplication: *mut IDXGIOutputDuplication,
       width: usize,
       height: usize,
       stage_texture: *mut ID3D11Texture2D,
   }

   impl DxgiCapturer {
       pub fn acquire_frame(&mut self, timeout_ms: u32) -> Result<FrameBuffer, CaptureError> {
           let mut frame_info: DXGI_OUTDUPL_FRAME_INFO = unsafe { std::mem::zeroed() };
           let mut desktop_resource: *mut IDXGIResource = std::ptr::null_mut();

           // 1. 尝试从 DWM 抓取最新一帧
           let hr = unsafe {
               (*self.duplication).AcquireNextFrame(
                   timeout_ms,
                   &mut frame_info,
                   &mut desktop_resource,
               )
           };

           if hr == DXGI_ERROR_WAIT_TIMEOUT {
               return Err(CaptureError::Timeout);
           } else if hr == DXGI_ERROR_ACCESS_LOST {
               // 显卡驱动重置、分辨率改变或 UAC 切换会导致访问权限丢失
               return Err(CaptureError::AccessLost);
           }

           // 2. 将桌面 GPU 纹理拷贝至可 CPU/编码器访问的 Staging Texture
           unsafe {
               let mut texture: *mut ID3D11Texture2D = std::ptr::null_mut();
               (*desktop_resource).QueryInterface(&IID_ID3D11Texture2D, &mut texture as *mut _ as *mut _);
               (*self.context).CopyResource(self.stage_texture as _, texture as _);
               (*texture).Release();
               (*desktop_resource).Release();
           }

           // 3. 归还帧缓冲所有权
           unsafe { (*self.duplication).ReleaseFrame() };

           Ok(FrameBuffer::from_staging(self.stage_texture, self.width, self.height))
       }
   }

.. warning:: DXGI_ERROR_ACCESS_LOST 容灾
   当发生以下事件时，DDA 接口会抛出 ``DXGI_ERROR_ACCESS_LOST``：
   
   * 用户按下 ``Ctrl + Alt + Del`` 或触发 UAC 提权提示，Windows 切换到安全桌面（Winlogon Desktop）。
   * 显示器分辨率、缩放比例发生变更，或插拔了外接显示器。
   * 显卡驱动发生重置（TDR）。
   
   RustDesk 底层必须捕获该错误码，彻底销毁旧的 ``IDXGIOutputDuplication``，并在目标桌面上重新执行初始化流程。

---
macOS 平台：Quartz Display Services 与 CGDisplayStream
---

在 macOS 环境下，RustDesk 依赖 CoreGraphics 框架中的 **Quartz Display Services** 与 **CGDisplayStream** 进行画面采集：

* **CGDisplayStream** 运行于独立的回调分发队列（Dispatch Queue）中。当 WindowServer 刷新显示帧时，触发用户注册的闭包函数。
* 帧数据封装于 ``IOSurface`` 引用中。``IOSurface`` 是 macOS 内核支持的跨进程共享显存对象，允许硬件视频编码器（VideoToolbox）零拷贝直接读取像素。

---
Linux 平台：X11 与 Wayland / PipeWire 的架构分化
---

Linux 桌面环境存在 X11 与 Wayland 两种完全不同的显示协议，RustDesk 在底层实现了自适应分支：

1. **X11 运行时**：
   使用 ``XShmGetImage`` 结合 MIT-SHM 扩展，将 X Server 显存中的根窗口像素写入客户端分配的 System V / POSIX 共享内存段，避免了传统套接字通信的协议序列化开销。
2. **Wayland 运行时**：
   Wayland 协议出于安全沙箱隔离原则，严禁客户端跨进程随意抓取其他窗口像素。RustDesk 通过 **XDG Desktop Portal** (``org.freedesktop.portal.ScreenCast``) 请求桌面推流权限，底层通过 **PipeWire** 多媒体框架建立共享文件描述符（DMA-BUF / Memfd），实现低延迟流式采集。

---
RustDesk ``scrap`` 跨平台 Trait 抽象模型
---

为了将异构操作系统的底层实现细节与上层视频编码管线解耦，RustDesk 在 ``libs/scrap`` 中提炼了统一的 Trait 抽象：

.. code-block:: rust
   :caption: libs/scrap/src/common/mod.rs 抽象定义

   pub trait TraitCapturer {
       /// 获取画面的宽度与高度
       fn width(&self) -> usize;
       fn height(&self) -> usize;

       /// 抓取下一帧像素数据（阻塞或带超时机制）
       /// 返回包含行步幅（Stride）的切片指针
       fn frame<'a>(&'a mut self, timeout_ms: Duration) -> Result<Frame<'a>, CaptureError>;
   }

   pub struct Frame<'a> {
       pub data: &'a [u8],
       pub width: usize,
       pub height: usize,
       pub stride: usize, // 内存对齐步幅，可能大于 width * 4 (RGBA)
   }

---
像素内存步幅（Stride）与色彩空间对齐
---

在实际工程中，抓屏获取的原始像素数据绝不能简单假设为连续的 ``width * height * 4`` 字节缓冲区：

.. math::

   	ext{Stride} = 	ext{AlignUp}(	ext{Width} 	imes 	ext{BytesPerPixel}, 	ext{Alignment})

* **显存对齐要求**：GPU 硬件在分配显存行时，通常要求以 64、128 或 256 字节对齐。
* **Padding 填充字节**：如果图像宽度不是对齐基数的整数倍，每行末尾会存在无效的填充字节。
* **色彩格式**：Windows DDA 默认输出 ``DXGI_FORMAT_B8G8R8A8_UNORM``（BGRA），而主流视频编码器（H.264/AV1）期望输入的为连续的 YUV420P 或 NV12 格式。在将数据送入编码器前，必须在去除 Padding 的同时完成色彩空间矩阵转换。

***
小结与下章导读
***

本章系统梳理了 RustDesk 跨平台屏幕捕获的物理基础，剖析了 Windows DDA、macOS Quartz、Linux X11/Wayland 的底层 API 机制，并揭示了 ``libs/scrap`` 的抽象设计与显存对齐细节。

在下一节中，我们将深入操作系统输入子系统：
* **《01.02 跨平台输入事件注入引擎与多端同步实现》**：解析 Windows ``SendInput``、Linux ``uinput/XTest`` 以及 macOS ``CGEvent`` 如何实现毫秒级键鼠事件的无损还原。
