======================================================================
02.04 动态码率自适应、丢包补偿与帧率平滑调度
======================================================================

.. note:: 前置背景与上下文承接
   在前面的章节中，我们先后构建了帧缓冲色彩空间转换与显存零拷贝流水线（《02.01》）、libvpx 与 libaom 软件实时编码器调优（《02.02》）以及跨平台 GPU 硬件加速编解码架构（《02.03》）。至此，受控端已具备在各种异构芯片上快速生成音视频压缩数据流的能力。然而，现实公网环境充斥着动态带宽抖动、瞬时丢包与缓冲区膨胀（Bufferbloat）。若编码器采用静态固定的码率和帧率推流，网络拥塞将瞬间导致数据包在路由器队列中积压，引发数十秒的画面严重滞后甚至连接中断。本章将深入剖析 RustDesk 在 ``src/server/video_qos.rs`` 与 ``src/server/video_service.rs`` 中的 **QoS（服务质量）动态调控引擎**，解构其往返时延（RTT）平滑估算、自适应码率（ABR）状态机与丢包补偿机制。

***
远程控制流媒体拥塞控制的物理挑战
***

不同于在线视频点播（VOD）可通过数十秒的客户端播放缓冲区吸收网络波动，远程桌面属于**交互式超低延迟控制流**：

1. **缓冲区膨胀敏感（Bufferbloat Sensitivity）**：当网络出现瓶颈时，若发送端持续以高于链路容量的速率推流，瓶颈路由器的 FIFO 队列会被迅速填满，产生高达数百毫秒的排队延迟（Queuing Delay）。
2. **多用户协同瓶颈（Multi-Client Concurrency）**：在多端同时协同查看受控主机时，单一弱网客户端可能拖垮服务端广播队列，必须实现多会话最小瓶颈对齐（Min-Filter Alignment）。
3. **静止与动态画面的剧烈方差**：桌面操作系统绝大多数时间处于画面几乎静止状态（仅光标微动），而在滚动网页、全屏播放视频或拖拽窗口时，瞬时像素变化率可达 100%。

.. list-table:: RustDesk QoS 关键控制参数与物理阈值
   :widths: 22 20 30 28
   :header-rows: 1

   * - 调控参数
     - 常量取值
     - 物理含义
     - 调控目标
   * - ``DELAY_THRESHOLD_150MS``
     - $150\,	ext{ms}$
     - 优良网络与拥塞网络的分界门限
     - 区分加速探测与降速避让
   * - ``ADJUST_RATIO_INTERVAL``
     - $3\,	ext{s}$
     - 码率比率调整评估周期
     - 消除高频震荡，维持稳态质量
   * - ``INIT_FPS`` / ``MAX_FPS``
     - $15\,	ext{FPS} / 120\,	ext{FPS}$
     - 连接初始帧率与上限帧率
     - 冷启动平稳握手，支持电竞级高刷
   * - ``WINDOW_SAMPLES``
     - $60\,	ext{Samples}$
     - RTT 历史观测滑动窗口深度
     - 消除网络瞬时噪声，提取真实链路基线

---
网络往返时延（RTT）与排队延迟平滑估算 (``RttCalculator``)
---

在衡量网络真实负载时，单纯单次测量的 Ping 值极易受到偶发抖动干扰。RustDesk 在 ``src/server/video_qos.rs`` 中设计了双重加权平滑滤波器 ``RttCalculator``：

.. math::

   	ext{SRTT} = (1 - \alpha) \cdot \min(	ext{RTT}_{	ext{historical}}) + \alpha \cdot \min(	ext{RTT}_{	ext{window}}) \quad (\alpha = 0.5)

.. code-block:: rust
   :caption: RttCalculator 双重最小时延滑动滤波（src/server/video_qos.rs）

   #[derive(Default, Debug, Clone)]
   struct RttCalculator {
       min_rtt: Option<u32>,        // 观测到的历史全局物理最小 RTT
       window_min_rtt: Option<u32>, // 最近 60 个采样窗口内的最小 RTT
       smoothed_rtt: Option<u32>,   // 加权平滑后的 RTT 估计值
       samples: VecDeque<u32>,      // 循环样本队列
   }

   impl RttCalculator {
       const WINDOW_SAMPLES: usize = 60;
       const ALPHA: f32 = 0.5;

       pub fn update(&mut self, delay: u32) {
           // 1. 更新历史最小传播时延
           match self.min_rtt {
               Some(min) if delay < min => self.min_rtt = Some(delay),
               None => self.min_rtt = Some(delay),
               _ => {}
           }
           // 2. 维护滑动窗口
           if self.samples.len() >= Self::WINDOW_SAMPLES {
               self.samples.pop_front();
           }
           self.samples.push_back(delay);
           self.window_min_rtt = self.samples.iter().min().copied();

           // 3. 计算排队隔离的加权平滑 RTT
           if self.samples.len() >= Self::WINDOW_SAMPLES {
               if let (Some(min), Some(w_min)) = (self.min_rtt, self.window_min_rtt) {
                   let new_srtt = ((1.0 - Self::ALPHA) * min as f32 + Self::ALPHA * w_min as f32) as u32;
                   self.smoothed_rtt = Some(new_srtt);
               }
           }
       }
   }

通过计算 $	ext{Queuing Delay} = 	ext{AvgDelay} - 	ext{RTT}$，QoS 控制器能够精准剥离出物理链路固有时延（如跨洋海底光缆延迟）与由网络拥塞引发的排队膨胀延迟。

---
自适应码率调控状态机 (ABR Engine)
---

RustDesk 的自适应码率调节（``adjust_ratio``）以 $3\,	ext{秒}$ 为评估周期，根据当前会话的最大延迟阶梯执行码率升降：

.. code-block:: rust
   :caption: 阶梯式码率自适应调控逻辑（src/server/video_qos.rs）

   fn adjust_ratio(&mut self, dynamic_screen: bool) {
       if !self.in_vbr_state() { return; }
       let Some(max_delay) = self.users.iter().map(|u| u.1.delay.avg_delay()).max() else { return; };
       let current_ratio = self.ratio;
       let mut v = current_ratio;

       // 根据排队时延阶梯执行乘性增减（AIMD 思想）
       if max_delay < 50 {
           if dynamic_screen { v = current_ratio * 1.15; } // 极佳网络：激进上探 15%
       } else if max_delay < 100 {
           if dynamic_screen { v = current_ratio * 1.10; } // 良好网络：适度上探 10%
       } else if max_delay < DELAY_THRESHOLD_150MS {
           if dynamic_screen { v = current_ratio * 1.05; } // 边界网络：平稳微调 5%
       } else if max_delay < 200 {
           v = current_ratio * 0.95; // 轻度拥塞：回退 5%
       } else if max_delay < 300 {
           v = current_ratio * 0.90; // 中度拥塞：回退 10%
       } else if max_delay < 500 {
           v = current_ratio * 0.85; // 重度拥塞：回退 15%
       } else {
           v = current_ratio * 0.80; // 严重排队：剧烈骤降 20%
       }

       // 限制最大增长步长（单周期增加不超过 150kbps），防止网络瞬时过冲
       if let Some(ratio_add_150kbps) = ratio_add_150kbps {
           if v > ratio_add_150kbps && ratio_add_150kbps > current_ratio && current_ratio >= BR_SPEED {
               v = ratio_add_150kbps;
           }
       }
       self.ratio = v.clamp(min, max);
       self.adjust_ratio_instant = Instant::now();
   }

.. math::

   	ext{Bitrate} = 	ext{BaseBitrate}(	ext{Width}, 	ext{Height}) 	imes 	ext{Ratio}

针对高分辨率（$2	ext{K}/4	ext{K}$）屏幕，QoS 算法设置了 $1\,	ext{Mbps}$ 的底线防护（``ratio_1mbps``），防止在恶劣网络下码率被过度压缩导致文字边缘严重模糊不可辨认。

---
动态帧率平滑调度 (Adaptive FPS Pacing)
---

除了调整画质码率，**动态调整帧间隔时间（Seconds Per Frame, SPF）** 是应对突发卡顿最有效的杠杆：

.. code-block:: rust
   :caption: 网络延迟感知的动态帧率调节（src/server/video_qos.rs）

   // 当网络延时超过 150ms 门限时，动态降频公式
   let dividend_ms = DELAY_THRESHOLD_150MS * min_fps;

   if avg_delay < 200 {
       fps = min_fps.max(devide_fps);
   } else if avg_delay < 300 {
       fps = min_fps.min(devide_fps);
   } else if avg_delay < 600 {
       fps = dividend_ms / avg_delay; // 反比例降低帧率，释放网络带宽
   } else {
       fps = (dividend_ms / avg_delay).min(devide_fps);
   }

1. **新会话冷启动抑制**：在客户端刚连接的第 $1$ 秒内，强制将帧率限制在 ``INIT_FPS = 15``，等待握手测量与 RTT 收敛后再逐步爬升。
2. **多端会话瓶颈收敛**：服务端推流频率严格遵循所有在线用户的最小帧率 $\min(	ext{user\_fps})$，彻底避免推流速率超出最慢客户端的消费能力而撑爆发送缓冲区。

---
丢包补偿与按需关键帧请求 (PLI / FIR)
---

在弱网 UDP 传输中，一旦某个 P 帧的部分切片丢失，由于现代视频编码的帧间参考依赖，后续所有 P 帧在解码端都会产生“花屏马赛克”并不断扩散。

RustDesk 舍弃了开销巨大的全局周期性 I 帧，采用**基于信令反馈的按需关键帧补偿架构**：

```
[受控端 VideoService]                              [主控端 Client Decoder]
          │                                                  │
          ├─ 1. 推流 P 帧序列 (P1, P2, P3...) ───────────────>│
          │                                                  ├─ 2. 检测到 RTP/UDP 丢包，解码器花屏
          │<─ 3. 信令通道发送 PLI (Picture Loss Indication) ──┤
          │                                                  │
          ├─ 4. 底层编码器强制插入瞬时 IDR/Keyframe ──────────>│
          │                                                  ├─ 5. 刷新参考帧缓存，画面恢复清晰
```

* **Picture Loss Indication (PLI)**：客户端在解码失败时通过低延迟控制通道向服务端回传 PLI 信号。
* **瞬时 IDR 帧强制注入**：编码器调用底层硬件接口（如 NVENC 的 ``NV_ENC_PIC_FLAG_FORCEIDR`` 或 libvpx 的 ``VPX_EFLAG_FORCE_KF``）立即输出完整关键帧，彻底切断错误扩散链。

***
小结与下章导读
***

至此，**模块 02：音视频媒体管线与编解码** 的四大核心基石已全部完工：
* 《02.01 帧缓冲对齐、色彩空间转换 (YUV/NV12) 与零拷贝模型》
* 《02.02 软件视频编码器集成与优化 (libvpx VP8/VP9, libaom AV1)》
* 《02.03 硬件加速编解码架构 (NVENC, QSV, AMF, VideoToolbox)》
* 《02.04 动态码率自适应、丢包补偿与帧率平滑调度》

音视频数据流已在受控端完成了高效采集、压缩与拥塞控制。

在接下来的 **模块 03：信令通道、Protobuf 与 NAT 穿透** 中，我们将深入网络传输层核心：
* **《03.01 Protobuf 协议模型设计与消息帧编解码》**：解析 RustDesk 跨平台通信的协议基石——基于 Google Protocol Buffers 的二进制消息封装、字段压缩与流式反序列化状态机。
