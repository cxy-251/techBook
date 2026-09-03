======================================================================
06.03 远程桌面画面渲染：GPU Texture 纹理共享与着色器流水线
======================================================================

.. note:: 前置背景与上下文承接
   在前一章《06.02 StreamSink 异步事件总线与 UI 状态同步模型》中，我们解剖了 RustDesk 如何通过双层事件总线与零拷贝指针双缓冲机制，将控制信令与像素到达信号无阻塞地广播给 Flutter 前端。然而，当远程画面达到 $4	ext{K}\,(3840 	imes 2160)$ 分辨率与 $60 \sim 144\,	ext{FPS}$ 高刷新率时，每秒产生的未压缩像素数据量高达：

   .. math::

      	ext{Data Rate} = 3840 	imes 2160 	imes 4\,	ext{Bytes (RGBA)} 	imes 60\,	ext{FPS} \approx 1.99\,	ext{GB/s}

   若采用传统软件渲染流水线（CPU 解码 $	o$ CPU 像素格式转换 $	o$ PCIe 主存到显存拷贝），将消耗超过 $40\%$ 的 CPU 算力与数吉字节的内存带宽，引发严重的掉帧与发热。如何实现从硬件解码器显存到 Flutter 渲染管线的**全链路零拷贝（Zero-Copy GPU Texture Sharing）**？本章将系统解剖 ``src/flutter.rs`` 中的纹理插件桥接、DirectX 11 / Metal / EGL 跨上下文显存共享句柄以及 GPU 着色器颜色空间转换流水线。

***
软件渲染瓶颈与 GPU 纹理直通物理架构
***

在传统的远程桌面客户端渲染中，数据在主机内存与显存之间存在多次冗余往返：

```
[传统软解拷贝路径 (高延迟/高 CPU 占用)]
   GPU 硬件解码 ─(显存到内存 D2H)─> 宿主内存 YUV ─(CPU 格式转换)─> 宿主内存 RGBA ─(内存到显存 H2D)─> GPU 纹理采样

[RustDesk GPU 纹理直通路径 (全链路显存零拷贝)]
   GPU 硬件解码 (NVDEC/QSV/AMF/VideoToolbox)
        │
        ▼ (显存内直接生成 ID3D11Texture2D / IOSurface / EGLImage)
   跨 API 显存共享句柄 (Shared Handle / Keyed Mutex)
        │
        ▼ (直接绑定至 Flutter Engine 渲染管线)
   GPU Pixel Shader (硬件着色器并行执行 YUV/NV12 -> sRGB 矩阵变换)
        │
        ▼
   屏幕物理显示 (Display VSync / SwapChain)
```

.. list-table:: 跨平台 GPU 纹理直通核心技术栈
   :widths: 20 25 28 27
   :header-rows: 1

   * - 操作系统
     - 硬件解码后端
     - 跨进程/跨 API 显存共享原语
     - Flutter 渲染直通机制
   * - **Windows**
     - D3D11VA / NVDEC / QSV / AMF
     - ``ID3D11Texture2D`` 共享句柄 + ``IDXGIKeyedMutex``
     - ``flutter_gpu_texture_renderer_plugin.dll``
   * - **macOS / iOS**
     - VideoToolbox (Hardware)
     - ``CVPixelBufferRef`` 绑定底层 ``IOSurface``
     - Metal ``MTLTexture`` 纹理直通
   * - **Linux**
     - VA-API / VDPAU
     - ``EGLImage`` + Linux DMA-BUF 跨进程导出
     - OpenGL / Vulkan 纹理外部绑定
   * - **Android**
     - MediaCodec (NDK)
     - ``AHardwareBuffer`` / ``SurfaceTexture``
     - OpenGLES 外部纹理 (``GL_TEXTURE_EXTERNAL_OES``)

---
Windows DirectX 11 显存共享句柄与 KeyedMutex 同步
---

在 Windows 平台上，Rust 视频解码工作线程与 Flutter UI 引擎通常处于不同的 DirectX 设备上下文中。为了在两套 Direct3D 设备之间安全共享显存纹理，RustDesk 依赖 Windows 现代图形驱动的 **DXGI 共享资源（Shared Resource Handle）** 与 **带键互斥锁（``IDXGIKeyedMutex``）**：

1. 显存共享与互斥访问时序
~~~~~~~~~~~~~~~~~~~~~~~~

```
[Rust 视频解码上下文 (Device A)]                     [Flutter 渲染引擎上下文 (Device B)]
                │                                                       │
   1. NVDEC 解码写入 ID3D11Texture2D                                    │
   2. 获取写入锁: KeyedMutex->AcquireSync(0, INFINITE)                  │
   3. 将解码帧拷贝至共享纹理                                            │
   4. 释放并转移锁: KeyedMutex->ReleaseSync(1) ─────────────────────────>│
                                                                        ├─ 5. 获取读取锁: KeyedMutex->AcquireSync(1, 0)
                                                                        ├─ 6. Flutter 合成器直接采样该纹理渲染
                                                                        └─ 7. 释放读取锁: KeyedMutex->ReleaseSync(0)
```

2. 插件符号动态加载与指针注册（``src/flutter.rs``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: rust
   :caption: GPU 纹理渲染插件符号绑定（src/flutter.rs）

   #[cfg(feature = "vram")]
   pub type FlutterGpuTextureRendererPluginCApiSetTexture =
       unsafe extern "C" fn(output: *mut c_void, texture: *mut c_void);

   #[cfg(feature = "vram")]
   pub fn on_texture(&self, display: usize, texture: *mut c_void) -> bool {
       let mut write_lock = self.map_display_sessions.write().unwrap();
       let Some(info) = write_lock.get_mut(&display) else {
           return false;
       };
       if info.gpu_output_ptr == usize::default() {
           return false;
       }
       if let Some(func) = &self.on_texture_func {
           // 直接向 Flutter 原生插件提交 GPU 显存纹理指针
           unsafe { func(info.gpu_output_ptr as _, texture) };
       }
       // 状态机记录当前为硬件纹理渲染模式
       info.notify_render_type = Some(RenderType::Texture);
       true
   }

---
GPU 着色器（Shader）颜色空间转换流水线
---

视频编解码器原生输出的像素格式为 **YUV420p** 或 **NV12（双平面：Y 平面 + UV 交错平面）**。若在 CPU 上将 YUV 逐像素转换为 RGBA，每秒需进行数十亿次浮点矩阵乘法运算。

在 GPU 纹理直通模式下，RustDesk 将这一重度计算全部卸载给 GPU 的**像素着色器（Pixel / Fragment Shader）**：

1. 色彩空间转换数学模型
~~~~~~~~~~~~~~~~~~~~~~

着色器通过硬件纹理单元并发采样 Y 纹理与 UV 纹理，并在 GPU ALU 中单时钟周期完成矩阵变换：

.. math::

   \begin{bmatrix} R \ G \ B \end{bmatrix} =
   \mathbf{M}_{	ext{CSC}} 	imes 
   \left( \begin{bmatrix} Y \ U \ V \end{bmatrix} - \begin{bmatrix} 	ext{Offset}_Y \ 128 \ 128 \end{bmatrix} \right)

* **BT.709 标准色彩矩阵（高清与 4K 远程桌面标准）**：

.. math::

   \begin{cases}
   R = 1.164383 	imes (Y - 16) + 1.792741 	imes (V - 128) \
   G = 1.164383 	imes (Y - 16) - 0.213249 	imes (U - 128) - 0.532909 	imes (V - 128) \
   B = 1.164383 	imes (Y - 16) + 2.112402 	imes (U - 128)
   \end{cases}

* **有限范围（Limited Range $[16, 235]$）与全范围（Full Range $[0, 255]$）自适应裁切**：着色器依据握手协商中的 ``Chroma`` 元数据动态调整量化偏移与缩放因子，彻底消除画面灰蒙或暗部细节丢失。

---
垂直同步 (VSync) 锁相与极限低时延（$< 8\,	ext{ms}$）
---

为了防止高速移动鼠标或滚动网页时出现画面撕裂（Tearing），同时避免双缓冲/三缓冲引入额外的输入延迟：

1. **三重缓冲（Triple-Buffering）与丢弃策略**：
   当解码速率临时高于屏幕刷新率时，未被呈现的旧缓冲帧被直接标记废弃，Flutter 渲染循环始终获取最新就绪的物理显存帧，消除显示器排队延迟；
2. **VSync 信号锁相驱动**：
   Flutter Engine 的渲染时钟由操作系统的 VSync 中断信号触发，显存纹理的提交与屏幕扫描线严格对齐，达成极致平滑且时延控制在 $8\,	ext{ms}$ 以内的工业级渲染表现。

***
小结与下章导读
***

至此，**模块 06：Rust-Flutter FFI 桥接与跨平台渲染** 的三大核心基石已全部完工：
* 《06.01 flutter_rust_bridge 架构与跨语言内存安全传递》
* 《06.02 StreamSink 异步事件总线与 UI 状态同步模型》
* 《06.03 远程桌面画面渲染：GPU Texture 纹理共享与着色器流水线》

客户端在跨语言调用、高频事件分发与极限图形渲染层面已构建起极具工业参考价值的现代跨平台架构。

在接下来的 **模块 07：服务端架构与中继调度** 中，我们将视野转向整个 RustDesk 生态的后端基础设施：
* **《07.01 注册与 ID 寻址服务器 (hbbs) 架构与 Peer 状态存储》**：系统解构开源注册服务器 ``hbbs`` 的高并发信令监听、Peer 全局在线状态机、K-V 缓存存储以及设备公钥证书管理。
