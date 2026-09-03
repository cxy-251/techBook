======================================================================
02.02 软件视频编码器集成与优化 (libvpx VP8/VP9, libaom AV1)
======================================================================

.. note:: 前置背景与上下文承接
   在前一章《02.01 帧缓冲对齐、色彩空间转换 (YUV/NV12) 与零拷贝模型》中，我们深入剖析了屏幕帧缓冲在 CPU/GPU 内存中的排布规则、基于 ``libyuv`` 的 SIMD 色彩空间转换，以及 VRAM 显存零拷贝流水线。然而，在云服务器、无独立显卡的虚拟化实例（如 VPS、Docker 容器）或驱动不支持硬件编码的低端设备上，系统必须依赖 **CPU 纯软件编码器** 作为高可用保底。软件编码面临着极高的算力挑战：如何在将 CPU 占用率控制在合理范围的前提下，实现毫秒级超低延迟实时编码？本章将深入剖析 RustDesk 在 ``libs/scrap/src/common/vpxcodec.rs`` 与 ``aom.rs`` 中对 **Google libvpx (VP8/VP9)** 与 **AOMedia libaom (AV1)** 软件编解码器的深度工程调优。

***
实时通信场景下的软件视频编码物理约束
***

不同于点播（VOD）或离线转码可以采用多多遍编码（Two-Pass）和深度前瞻缓冲（Lookahead），远程桌面系统属于典型的**极低延迟交互式实时通信（Interactive Real-Time Communication）**。其对软件编码器提出了严苛的物理限制：

1. **单帧编码时间必须 $< 15\,	ext{ms}$**：为了维持 60 FPS 流畅交互，抓屏、色彩转换、编码、网络传输与解码渲染的端到端预算通常在 $30\,	ext{ms} \sim 50\,	ext{ms}$ 以内，留给 CPU 软件编码的窗口极窄。
2. **零前瞻延迟（Zero Lookahead / Zero Lag）**：必须禁用跨帧的前向分析缓冲（``g_lag_in_frames = 0``），输入一帧必须立刻输出对应压缩包（Packet）。
3. **消除周期性关键帧（No Periodic Keyframes）**：常规视频每隔 1~2 秒插入一个庞大的 I 帧（Intra Frame），而 I 帧体积通常是 P 帧的 5~10 倍，会导致网络产生巨大的瞬时码率尖峰（Burst）。远程桌面必须采用**按需关键帧（On-Demand Keyframe）**机制，仅在连接初始化或严重丢包导致解码器崩溃时才触发关键帧生成。

.. list-table:: RustDesk 支持的三大软件编码器特性对比
   :widths: 18 22 30 30
   :header-rows: 1

   * - 编码格式
     - 核心底层库
     - 压缩效率与算法复杂度
     - 核心调优特性与适用场景
   * - **VP8**
     - ``libvpx``
     - 较低复杂度，兼容性极高
     - 适用于老旧 CPU、低功耗移动端或超轻量算力环境
   * - **VP9**
     - ``libvpx``
     - 相比 VP8 节省约 30%~40% 码率
     - 支持 Tile 多线程分片与行级并行（Row-MT），支持 I444 采样
   * - **AV1**
     - ``libaom``
     - 压缩率天花板，相比 VP9 再提升 20%~30%
     - 专为屏幕共享（Screen Content）引入调优策略与调色板模式（Palette Mode）

---
libvpx (VP8/VP9) 实时参数调优与多线程分片
---

在 ``libs/scrap/src/common/vpxcodec.rs`` 中，RustDesk 针对实时远程桌面通信定制了 libvpx 的核心控制参数。

1. 恒定码率（CBR）与抗丢包丢帧门限
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: rust
   :caption: libvpx 实时编码上下文配置（libs/scrap/src/common/vpxcodec.rs）

   c.g_timebase.num = 1;
   c.g_timebase.den = 1000; // 毫秒级时间戳精度
   c.rc_undershoot_pct = 95;

   // 丢帧阈值：当缓冲区充盈度过低时触发主动丢帧，动态场景下平滑网络抖动
   c.rc_dropframe_thresh = 25;
   c.g_threads = codec_thread_num(64) as _;
   c.g_error_resilient = VPX_ERROR_RESILIENT_DEFAULT;

   // 强制采用实时恒定码率模式（CBR）
   c.rc_end_usage = vpx_rc_mode::VPX_CBR;

   // 禁用周期性关键帧，大幅削减稳态带宽占用
   if let Some(keyframe_interval) = config.keyframe_interval {
       c.kf_min_dist = 0;
       c.kf_max_dist = keyframe_interval as _;
   } else {
       c.kf_mode = vpx_kf_mode::VPX_KF_DISABLED;
   }

2. 动态量化参数 ($Q_{\min}, Q_{\max}$) 自适应插值
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

RustDesk 通过质量比率（Quality Ratio）对量化参数 QP 进行双向动态钳制：

.. code-block:: rust
   :caption: VP8/VP9 动态 QP 范围计算

   fn calc_q_values(ratio: f32) -> (u32, u32) {
       let b = (ratio * 100.0) as u32;
       let b = std::cmp::min(b, 200);
       let q_min1 = 36;
       let q_min2 = 0;
       let q_max1 = 56;
       let q_max2 = 37;

       let t = b as f32 / 200.0;
       let mut q_min: u32 = ((1.0 - t) * q_min1 as f32 + t * q_min2 as f32).round() as u32;
       let mut q_max = ((1.0 - t) * q_max1 as f32 + t * q_max2 as f32).round() as u32;

       (q_min.clamp(q_min2, q_min1), q_max.clamp(q_max2, q_max1))
   }

3. Tile 分块与行级多线程并行（Row-MT）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了榨干多核 CPU 的并行算力，VP9 允许将画面拆分为多个独立的矩形区块（Tiles）：

.. code-block:: rust
   :caption: VP9 实时 CPU 档位与分片并行控制

   if config.codec == VpxVideoCodecId::VP9 {
       // 设置 CPU 速度档位：实时通信推荐档位 7~8（降低复杂度，压低延迟）
       call_vpx!(vpx_codec_control_(&mut ctx, VP8E_SET_CPUUSED as _, 7));
       
       // 开启行级多线程（Row-Level Multithreading）
       call_vpx!(vpx_codec_control_(&mut ctx, VP9E_SET_ROW_MT as _, 1 as c_int));
       
       // 设置 Tile 列数（4 列并行分片）
       call_vpx!(vpx_codec_control_(&mut ctx, VP9E_SET_TILE_COLUMNS as _, 4 as c_int));
   } else if config.codec == VpxVideoCodecId::VP8 {
       // VP8 模式下设置极端速度档位 12
       call_vpx!(vpx_codec_control_(&mut ctx, VP8E_SET_CPUUSED as _, 12));
   }

---
libaom (AV1) 屏幕内容感知优化（Screen Content Tools）
---

AV1 拥有新一代视频编码标准中最先进的屏幕编码工具集。在 ``libs/scrap/src/common/aom.rs`` 中，RustDesk 引入了 WebRTC 级别的实时优化配置。

1. 零前瞻与实时模式配置
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: rust
   :caption: libaom 实时参数基线配置（libs/scrap/src/common/aom.rs）

   c.g_usage = AOM_USAGE_REALTIME;
   c.g_pass = aom_enc_pass::AOM_RC_ONE_PASS;
   c.g_lag_in_frames = 0; // 强制禁用 Lookahead，杜绝帧缓冲堆积延迟
   c.rc_end_usage = aom_rc_mode::AOM_CBR;

   // 分辨率自适应 CPU 速度档位（6~10）
   let cpu_speed = if width * height <= 320 * 180 {
       8
   } else if width * height <= 640 * 360 {
       9
   } else {
       10
   };
   call_ctl!(ctx, AOME_SET_CPUUSED, cpu_speed);

2. 屏幕内容专属编码工具（Screen Content Tuning）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

远程桌面画面充斥着大面积纯色背景、细小代码字体与锐利窗口边缘，这与自然摄像机拍摄的真实世界视频完全不同。RustDesk 开启了 AV1 的屏幕优化矩阵：

.. code-block:: rust
   :caption: AV1 屏幕共享特性控制指令集

   // 1. 开启屏幕内容调优模型
   call_ctl!(ctx, AV1E_SET_TUNE_CONTENT, AOM_CONTENT_SCREEN);

   // 2. 开启调色板模式（Palette Mode）：对大面积纯色块与图标进行基色索引编码，极大压缩文本区域数据量
   call_ctl!(ctx, AV1E_SET_ENABLE_PALETTE, 1);

   // 3. 关闭自然运动补偿等重度复杂算法，防止 CPU 算力过载
   call_ctl!(ctx, AV1E_SET_ENABLE_OBMC, 0);          // 禁用重叠块运动补偿
   call_ctl!(ctx, AV1E_SET_ENABLE_WARPED_MOTION, 0); // 禁用仿射变换运动补偿
   call_ctl!(ctx, AV1E_SET_ENABLE_GLOBAL_MOTION, 0); // 禁用全局运动估计
   call_ctl!(ctx, AV1E_SET_DISABLE_TRELLIS_QUANT, 1);// 禁用网格量化（加速量化计算）

   // 4. 开启约束方向增强滤波（CDEF）与行级多线程（Row-MT）
   call_ctl!(ctx, AV1E_SET_ENABLE_CDEF, 1);
   call_ctl!(ctx, AV1E_SET_ROW_MT, 1);

---
Rust 零拷贝封装与 FFI 内存安全生命周期
---

为了避免在调用 C 动态库（libvpx / libaom）时发生额外的内存分配，RustDesk 实现了基于结构体包裹（Wrap）的零拷贝流水线：

.. code-block:: rust
   :caption: vpx_img_wrap / aom_img_wrap 原地指针映射

   // 1. 直接将 Rust 的切片指针借用给 C 结构体，零堆内存分配
   let mut image: vpx_image_t = Default::default();
   call_vpx_ptr!(vpx_img_wrap(
       &mut image,
       fmt,
       self.width as _,
       self.height as _,
       stride_align as _,
       data.as_ptr() as _, // 原始 YUV 内存切片指针
   ));

   // 2. 提交编码
   call_vpx!(vpx_codec_encode(
       &mut self.ctx,
       &image,
       pts as _,
       1,
       0,
       VPX_DL_REALTIME as _,
   ));

   // 3. 通过 Iterator 安全提取编码后的数据包包切片
   impl<'a> Iterator for EncodeFrames<'a> {
       type Item = EncodeFrame<'a>;
       fn next(&mut self) -> Option<Self::Item> {
           loop {
               unsafe {
                   let pkt = vpx_codec_get_cx_data(self.ctx, &mut self.iter);
                   if pkt.is_null() { return None; }
                   if (*pkt).kind == VPX_CODEC_CX_FRAME_PKT {
                       let f = &(*pkt).data.frame;
                       return Some(Self::Item {
                           data: slice::from_raw_parts(f.buf as _, f.sz as _),
                           key: (f.flags & VPX_FRAME_IS_KEY) != 0,
                           pts: f.pts,
                       });
                   }
               }
           }
       }
   }

通过 RAII ``Drop``  trait，Rust 保证了在编码器结构体脱离作用域时，严格调用 ``vpx_codec_destroy`` 与 ``aom_codec_destroy``，杜绝了长时间运行下的 C 运行时显存/内存泄漏。

***
小结与下章导读
***

本章系统解剖了 RustDesk 纯软件编解码器流水线的工程实现：
* 阐述了实时通信下软件编码器在帧延迟、零前瞻与按需关键帧上的核心物理约束。
* 剖析了 libvpx 在 VP8/VP9 模式下的 CBR 码率控制、动态 QP 线性插值与 Tile/Row-MT 行级多线程并行。
* 揭示了 libaom 在 AV1 模式下的屏幕内容感知优化（``AOM_CONTENT_SCREEN``、调色板模式 ``Palette Mode`` 与快速剪枝策略）。
* 展示了 Rust-C FFI 边界上的零拷贝指针包裹与 RAII 资源回收模型。

在下一节中，我们将探索 GPU 硬件编码器的极致性能释放：
* **《02.03 硬件加速编解码架构 (NVENC, QSV, AMF, VideoToolbox)》**：深入剖析跨厂商专用 ASIC 硬件编解码芯片的异步调度、动态码率重配置与硬件崩溃容灾切换机制。
