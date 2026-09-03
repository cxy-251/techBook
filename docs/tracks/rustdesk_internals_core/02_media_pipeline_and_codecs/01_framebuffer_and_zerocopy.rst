======================================================================
02.01 帧缓冲对齐、色彩空间转换 (YUV/NV12) 与零拷贝模型
======================================================================

.. note:: 前置背景与上下文承接
   在模块 01 中，我们全面剖析了操作系统底层的屏幕抓取、输入注入、音频环回与虚拟显示驱动。至此，受控端已能以极高的刷新率从图形合成器（如 Windows DWM、Linux Wayland）中获取原始屏幕像素表面。然而，捕获到的原始数据通常是高位宽的未压缩格式（如 32 位的 ``BGRA`` 或 ``RGBA``）。以 $4	ext{K}\,(3840 	imes 2160)$ 60FPS 为例，未经压缩的原始像素带宽高达：
   
   .. math::

      3840 	imes 2160 	imes 4\,	ext{Bytes} 	imes 60\,	ext{FPS} \approx 1.99\,	ext{GB/s}\,(15.9\,	ext{Gbps})

   如此庞大的数据吞吐量既不可能直接通过网络传输，更会在 CPU 内存与 GPU 显存之间造成严重的 PCIe 总线阻塞。本章将深入 RustDesk 的多媒体核心库 ``libs/scrap/src/common/``（重点包括 ``convert.rs``、``vram.rs`` 与 ``codec.rs``），解构帧缓冲行步幅对齐、SIMD 硬件加速的 RGB/YUV 色彩空间矩阵转换，以及显存级（VRAM）零拷贝流水线。

***
帧缓冲物理内存拓扑与步幅对齐（Stride Alignment）
***

在计算机图形硬件中，线性帧缓冲并非简单的连续紧凑数组。由于 GPU 显存控制器和 SIMD 指令集（如 AVX2、AVX-512、ARM NEON）在读取 $64$ 或 $128$ 字节对齐的内存地址时吞吐量最大，图形驱动通常会对每一行像素末尾追加填充字节（Padding Bytes）。

.. math::

   	ext{Stride} \ge 	ext{Width} 	imes 	ext{BytesPerPixel}

如果一个图像的物理分辨率为 $1920 	imes 1080$，采用 32 位 ``BGRA``（$4\,	ext{Bytes/Pixel}$），有效数据宽度为 $7680\,	ext{Bytes}$。但如果显卡驱动强制要求 $256\,	ext{Bytes}$ 边界对齐，实际分配的行步幅（Stride）将被向上对齐至 $7680\,	ext{Bytes}$（若宽度为 $1921$，步幅则会膨胀为 $7936\,	ext{Bytes}$）。

.. code-block:: rust
   :caption: 帧缓冲有效长度与行步幅边界安全校验（libs/scrap/src/common/convert.rs）

   if src_pixfmt == crate::Pixfmt::BGRA
       || src_pixfmt == crate::Pixfmt::RGBA
       || src_pixfmt == crate::Pixfmt::RGB565LE
   {
       // 校验步幅是否满足单行最小物理字节数
       if src_stride[0] < src_width * src_pixfmt.bytes_per_pixel() {
           bail!(
               "src_stride too small: {} < {}",
               src_stride[0],
               src_width * src_pixfmt.bytes_per_pixel()
           );
       }
       // 校验显存映射区实际切片长度是否覆盖全部扫描行，杜绝越界读取
       if src.len() < src_stride[0] * src_height {
           bail!(
               "wrong src len, {} < {} * {}",
               src.len(),
               src_stride[0],
               src_height
           );
       }
   }

---
色彩空间数学模型与下采样格式（I420 / NV12 / I444）
---

主流视频编码标准（H.264、H.265、VP9、AV1）均基于 **YCbCr / YUV 色彩空间**。人眼视网膜对亮度（Luminance, $Y$）的敏感度远高于色度（Chrominance, $U/V$），因此可以通过色彩下采样大幅削减数据量。

1. RGB 到 YUV 矩阵变换标准 (BT.601 / BT.709)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

根据 ITU-R BT.601 标准，标准动态范围下的模拟信号转换公式为：

.. math::

   \begin{aligned}
   Y  &= 0.299\,R + 0.587\,G + 0.114\,B \
   U  &= -0.1687\,R - 0.3313\,G + 0.5\,B + 128 \
   V  &= 0.5\,R - 0.4187\,G - 0.0813\,B + 128
   \end{aligned}

2. 三大 YUV 内存布局解剖
~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 常见 YUV 格式物理布局与适用场景
   :widths: 15 25 35 25
   :header-rows: 1

   * - 格式
     - 采样结构
     - 内存组织方式 (Memory Layout)
     - 核心应用场景
   * - **I420 (YUV420P)**
     - 4:2:0 (水平与垂直色度均减半)
     - 纯平面格式（Planar）：$[Y\,	ext{Plane}] 	o [U\,	ext{Plane}] 	o [V\,	ext{Plane}]$
     - 软件编码器（libvpx VP8/VP9, libaom AV1）标准输入
   * - **NV12**
     - 4:2:0 (色度交错)
     - 半平面格式（Semi-Planar）：$[Y\,	ext{Plane}] 	o [UVUV\dots\,	ext{Interleaved Plane}]$
     - 硬件编码器（Intel QSV, NVIDIA NVENC, AMD AMF）原生输入
   * - **I444 (YUV444P)**
     - 4:4:4 (色度无下采样)
     - 纯平面格式：$[Y\,	ext{Plane}] 	o [U\,	ext{Plane}] 	o [V\,	ext{Plane}]$，三平面尺寸完全一致
     - 远程开发、高精度文本渲染与专业设计（消除红蓝文字边缘伪影）

.. math::

   	ext{Data Ratio}_{	ext{I420/NV12}} = \frac{1 + 0.25 + 0.25}{4} = \frac{1.5}{4} = 37.5\%\,	ext{of raw BGRA}

---
SIMD 向量化加速色彩转换实现 (``libyuv`` 集成)
---

逐像素浮点矩阵运算开销极大。RustDesk 深度整合了 Google 开源的高性能多媒体处理库 **libyuv**，通过编译期生成 FFI 绑定（``yuv_ffi.rs``），在运行时根据 CPU 指令集特性动态分发 AVX2、SSSE3 或 ARM NEON 汇编实现。

.. code-block:: rust
   :caption: libyuv 高性能色彩空间转换调度（libs/scrap/src/common/convert.rs）

   pub fn convert_to_yuv(
       captured: &PixelBuffer,
       dst_fmt: EncodeYuvFormat,
       dst: &mut Vec<u8>,
       mid_data: &mut Vec<u8>,
   ) -> ResultType<()> {
       let align = |x: usize| (x + 63) / 64 * 64; // 保证 64 字节对齐
       
       match (src_pixfmt, dst_fmt.pixfmt) {
           (crate::Pixfmt::BGRA, crate::Pixfmt::I420) => {
               let dst_stride_y = dst_fmt.stride[0];
               let dst_stride_uv = dst_fmt.stride[1];
               dst.resize(dst_fmt.h * dst_stride_y * 2, 0);
               
               let dst_y = dst.as_mut_ptr();
               let dst_u = dst[dst_fmt.u..].as_mut_ptr();
               let dst_v = dst[dst_fmt.v..].as_mut_ptr();
               
               // 调用 libyuv AVX2/NEON 汇编函数 ARGBToI420
               call_yuv!(ARGBToI420(
                   src.as_ptr(),
                   src_stride[0] as _,
                   dst_y,
                   dst_stride_y as _,
                   dst_u,
                   dst_stride_uv as _,
                   dst_v,
                   dst_stride_uv as _,
                   src_width as _,
                   src_height as _,
               ));
           }
           (crate::Pixfmt::BGRA, crate::Pixfmt::NV12) => {
               let dst_stride_y = dst_fmt.stride[0];
               let dst_stride_uv = dst_fmt.stride[1];
               dst.resize(align(dst_fmt.h) * (align(dst_stride_y) + align(dst_stride_uv / 2)), 0);
               
               let dst_y = dst.as_mut_ptr();
               let dst_uv = dst[dst_fmt.u..].as_mut_ptr();
               
               // 调用 libyuv 硬件加速函数 ARGBToNV12
               call_yuv!(ARGBToNV12(
                   src.as_ptr(),
                   src_stride[0] as _,
                   dst_y,
                   dst_stride_y as _,
                   dst_uv,
                   dst_stride_uv as _,
                   src_width as _,
                   src_height as _,
               ));
           }
           _ => bail!("Unsupported pixel format conversion"),
       }
       Ok(())
   }

---
VRAM 显存级零拷贝架构（Hardware Zero-Copy Pipeline）
---

传统的多媒体处理链路通常包含多次昂贵的主机内存与设备显存之间的 PCIe DMA 传输：

$$	ext{GPU 渲染 VRAM} \xrightarrow{	ext{D2H 拷贝}} 	ext{CPU 内存 (RAM)} \xrightarrow{	ext{色彩转换}} 	ext{CPU 内存} \xrightarrow{	ext{H2D 拷贝}} 	ext{GPU 编码 VRAM}$$

每一次 PCIe 往返都会占用数毫秒的总线延迟与 CPU 缓存带宽。

1. 共享纹理句柄（Shared Texture Handle）直通
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

RustDesk 在 Windows 和 Linux 平台实现了真正的 **VRAM 显存内零拷贝架构**（``libs/scrap/src/common/vram.rs``）：

```
[Direct3D11 / DXGI Desktop Duplication]
               │ (GPU 显存内直接生成)
      [ID3D11Texture2D 表面]
               │
               ├─ 1. 提取 Direct3D 共享句柄 / 显存指针
               │
               ▼
[NVIDIA NVENC / Intel QSV / AMD AMF 硬件编码器]
               │ (显卡内部引擎直接读取 Texture，无需 PCIe 回传 CPU)
               ▼
        [输出 H.264 / H.265 NAL 报文]
```

.. code-block:: rust
   :caption: VRAM 硬件编码器直接消费 GPU 纹理指针（libs/scrap/src/common/vram.rs）

   impl EncoderApi for VRamEncoder {
       fn encode_to_message(
           &mut self,
           frame: EncodeInput,
           ms: i64,
       ) -> ResultType<VideoFrame> {
           // 1. 直接提取显存纹理指针（如 *mut ID3D11Texture2D）
           let (texture, rotation) = frame.texture()?;
           if rotation != 0 {
               bail!("rotation not supported");
           }
           
           let mut vf = VideoFrame::new();
           let mut frames = Vec::new();
           
           // 2. 显卡芯片内部硬件编码引擎直接读取该 VRAM 纹理
           for frame in self.encode(texture, ms).with_context(|| "Failed to encode")? {
               frames.push(EncodedVideoFrame {
                   data: Bytes::from(frame.data),
                   pts: frame.pts,
                   key: frame.key == 1,
                   ..Default::default()
               });
           }
           // 3. 封装为 Protobuf 报文返回...
           Ok(vf)
       }
   }

2. 多显卡拓扑与 LUID 适配路由
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在搭载双显卡（如 Intel 集显 + NVIDIA 独显）的主机上，抓屏设备（DXGI Output）与编码设备必须处于同一块物理 GPU 上，否则跨 GPU 显存访问将导致驱动严重卡死。

RustDesk 通过检查显卡唯一标识符 **LUID（Locally Unique Identifier）** 实现拓扑对齐：

.. code-block:: rust
   :caption: 多显卡 LUID 对齐与可用性验证

   let luids = displays.iter().map(|d| d.adapter_luid()).collect::<Vec<_>>();
   if luids.iter().all(|luid| v.iter().any(|f| Some(f.luid) == *luid)) {
       // 仅当所有活动显示器绑定的 GPU 均支持硬件显存编码时才激活 VRAM 模式
       v
   } else {
       log::info!("not all adapters support VRAM encode, fallback to RAM");
       vec![]
   }

若拓扑不匹配，系统平滑回退至内存中转模式（RAM Encoder），确保系统绝对稳定。

***
小结与下章导读
***

本章深入解构了 RustDesk 多媒体流水线中的数据规整与零拷贝加速机制：
* 阐明了帧缓冲物理对齐（Stride）的内存安全校验与计算逻辑。
* 剖析了 RGB 与 I420/NV12/I444 色彩空间的数学转换模型，以及通过 ``libyuv`` 进行 SIMD 汇编向量化加速的工程实现。
* 解构了基于 Direct3D11 共享纹理与显卡 LUID 拓扑对齐的 **VRAM 显存级零拷贝推流流水线**。

在下一节中，我们将深入软件编码器内核：
* **《02.02 软件视频编码器集成与优化 (libvpx VP8/VP9, libaom AV1)》**：解析在无独立显卡或受限 CPU 环境下，RustDesk 如何调优 libvpx 与 libaom 的实时参数（多线程分片、动态量化参数 QP、实时速度预设 Speed Preset 与低延迟模式）。
