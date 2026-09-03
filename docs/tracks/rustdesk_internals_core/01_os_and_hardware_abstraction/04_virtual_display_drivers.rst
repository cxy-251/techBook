======================================================================
01.04 IddCx 虚拟显示驱动与隐私屏黑屏机制
======================================================================

.. note:: 前置背景与上下文承接
   在前三章中，我们分别解剖了远程桌面的核心输入输出交互原语：屏幕像素捕获（《01.01》）、输入事件仿真注入（《01.02》）以及音频环回捕获（《01.03》）。至此，常规远程连接的声、画、控流水线已全部建立。然而，在工业与企业级远程控制场景中，系统往往面临两大极端边界挑战：
   
   1. **无头服务器（Headless Server）**：受控主机未连接任何物理显示器，导致显卡驱动与 DWM（桌面窗口管理器）降级为基础渲染模式，无法开启硬件加速或锁定在极低分辨率（如 $640 	imes 480$）；
   2. **受控端隐私安全（Privacy Mode）**：主控端在远程操作涉密文件时，要求受控端的物理显示器黑屏且屏蔽本地键鼠，防止现场人员窥探与误触。
   
   本章将深入剖析 RustDesk 在 ``src/virtual_display_manager.rs``、``libs/virtual_display`` 与 ``src/privacy_mode/`` 中的实现，系统解构基于 **IddCx（Indirect Display Driver）** 虚拟显示驱动与系统级屏幕安全遮蔽的底层物理机制。

***
无头服务器渲染困境与 IddCx 驱动架构
***

在物理显示器未接入显卡接口（HDMI/DP/DVI）时，GPU 无法通过 I2C/DDC 总线读取显示器的 **EDID（Extended Display Identification Data）** 元数据。缺乏 EDID 将导致操作系统图形堆栈产生连锁反应：

* **Windows**: DWM 禁用 Direct3D 硬件加速，DXGI Desktop Duplication 接口抛出 ``DXGI_ERROR_UNSUPPORTED``，系统退化为纯 CPU 软件渲染。
* **Linux (X11/Wayland)**: X Server 或 DRM/KMS 无法分配 CRTC（Cathode Ray Tube Controller）扫描控制器，导致帧缓冲大小无法动态拉伸。

为了彻底突破物理硬件的束缚，Windows 10（19041 及以上）引入了 **间接显示驱动模型（Indirect Display Driver Model, IddCx）**。

.. list-table:: 传统虚拟显卡与 IddCx 间接显示驱动对比
   :widths: 20 25 30 25
   :header-rows: 1

   * - 技术方案
     - 运行模式 (Ring)
     - 显卡渲染管道 (Pipeline)
     - 稳定性与内核风险
   * - **传统 XDDM / WDDM 驱动**
     - 内核态 (Ring 0)
     - 侵入操作系统显卡调度链路
     - 易引发系统蓝屏（BSOD），需要微软 WHQL 签名
   * - **IddCx 用户态驱动**
     - 用户态 (Ring 3 UMDF)
     - GPU 物理硬件正常渲染 $	o$ IddCx 捕获合成帧
     - 隔离于用户空间，崩溃不影响操作系统内核稳定性

---
RustDesk IddCx 驱动接入与无头模式动态注入
---

RustDesk 在 ``src/virtual_display_manager.rs`` 中集成了自主研发的 ``RustDeskIddDriver`` 与开源 Amyuni ``usbmmidd`` 驱动。其核心在于通过 Windows SetupAPI 动态创建虚拟硬件设备节点，并通过 ``DeviceIoControl`` 发送 IOCTL 控制码模拟物理显示器的热插拔（Hot-Plug）。

1. 虚拟设备创建与驱动安装
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: rust
   :caption: IddCx 驱动初始化与设备注册（src/virtual_display_manager.rs）

   pub const RUSTDESK_IDD_DEVICE_STRING: &'static str = "RustDeskIddDriver Device\0";

   impl VirtualDisplayManager {
       fn install_update_driver(&mut self) -> ResultType<()> {
           // 1. 创建虚拟设备根节点
           if let Err(e) = virtual_display::create_device() {
               if !e.to_string().contains("Device is already created") {
                   bail!("Create device failed {}", e);
               }
           }
           // 2. 通过 SetupAPI / INF 注册并加载 UMDF IddCx 驱动
           let mut _reboot_required = false;
           virtual_display::install_update_driver(&mut _reboot_required)?;
           self.is_driver_installed = true;
           Ok(())
       }
   }

2. 无头模式热插拔与分辨率注入 (``plug_in_headless``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当检测到受控端无物理显示器或主控端发起虚拟屏幕请求时，服务向 IddCx 驱动注入虚拟 EDID 结构与支持的显示模式列表（Monitor Modes）：

.. code-block:: rust
   :caption: 注入虚拟分辨率与设备名差分探测

   pub fn plug_in_headless() -> ResultType<()> {
       let mut manager = VIRTUAL_DISPLAY_MANAGER.lock().unwrap();
       manager.prepare_driver()?;

       // 注入默认 1080P 60Hz 虚拟显示模式
       let modes = [virtual_display::MonitorMode {
           width: 1920,
           height: 1080,
           sync: 60,
       }];

       let device_names = get_device_names().into_iter().collect();
       // 向驱动发送热插拔指令（VIRTUAL_DISPLAY_INDEX_FOR_HEADLESS = 0）
       VirtualDisplayManager::plug_in_monitor(VIRTUAL_DISPLAY_INDEX_FOR_HEADLESS, &modes)?;

       // 差分探测新生成的 DISPLAY_DEVICE 设备名（如 \.\DISPLAY2）
       let device_name = get_new_device_name(&device_names);
       manager.headless_index_name = Some((VIRTUAL_DISPLAY_INDEX_FOR_HEADLESS, device_name));
       Ok(())
   }

通过将虚拟显示器插入图形子系统，Windows DWM 会立刻将其视作一台真实的物理显示器，为其分配桌面表面并重新激活 Direct3D / DXGI 硬件加速捕获管线。

---
隐私模式（Privacy Mode）的双重实现架构
---

在远程控制中，实现受控端“物理屏幕变黑，主控端画面正常推流”存在极高的技术难度：**如果操作系统画面被全黑覆盖，传统的 DXGI 抓屏也会抓取到全黑画面**。

RustDesk 在 ``src/privacy_mode/`` 中构建了两种截然不同但高度可靠的技术路径：

1. **方案 A：虚拟屏幕拓扑迁移与物理显示器下线（``win_virtual_display.rs``）**
2. **方案 B：DXGI 抓屏排除与置顶黑屏遮罩（``win_exclude_from_capture.rs`` / ``win_topmost_window.rs``）**

---
方案 A 深入：虚拟显示器拓扑置换与注册表恢复
---

这是最彻底、抗截屏能力最强的隐私模式。其底层状态机如下：

```
[开启隐私模式]
      │
      ├─ 1. 插入一块 IddCx 虚拟显示器 (Virtual Display)
      ├─ 2. 将虚拟显示器提升为主显示器 (CDS_SET_PRIMARY)
      ├─ 3. 将所有物理显示器移出桌面可视区域 (dmPosition=(10000,10000), dmPels=(0,0))
      ├─ 4. 提交图形拓扑变更 (ChangeDisplaySettingsExW) ──> 物理显示器进入休眠/黑屏
      ├─ 5. 挂钩本地输入 (win_input::hook) ──> 屏蔽现场键鼠
      │
[远程操作中] ── 仅抓取并推流虚拟显示器渲染内容
      │
[退出隐私模式 / 异常断开]
      │
      └─ 6. RAII Guard / 注册表快照还原物理显示器原始坐标与分辨率
```

.. code-block:: rust
   :caption: 物理显示器移出桌面与分辨率清零（src/privacy_mode/win_virtual_display.rs）

   fn disable_physical_displays(&self) -> ResultType<()> {
       for display in &self.displays {
           let mut dm = display.dm.clone();
           unsafe {
               // 将物理屏幕逻辑坐标移至 (10000, 10000) 远离主屏幕工作区
               dm.u1.s2_mut().dmPosition.x = 10000;
               dm.u1.s2_mut().dmPosition.y = 10000;
               // 将像素宽高设为 0，通知 DWM 卸载该物理输出端点
               dm.dmPelsHeight = 0;
               dm.dmPelsWidth = 0;
               let flags = CDS_UPDATEREGISTRY | CDS_NORESET;
               let rc = ChangeDisplaySettingsExW(
                   display.name.as_ptr(),
                   &mut dm,
                   NULL as _,
                   flags,
                   NULL as _,
               );
               if rc != DISP_CHANGE_SUCCESSFUL {
                   let err = Self::change_display_settings_ex_err_msg(rc);
                   bail!("Failed ChangeDisplaySettingsEx, {}", err);
               }
           }
       }
       Ok(())
   }

.. warning:: 显示拓扑异常容灾与 RAII 保护 (TurnOnGuard)
   如果在物理显示器关闭后，网络发生突发断开或进程崩溃，受控端可能永久停留在“黑屏无物理输出”状态。RustDesk 引入了 **RAII ``TurnOnGuard``** 并在注册表（``reg_display_settings``）中持久化保存进入隐私模式前的显示器配置快照。一旦会话异常销毁，系统看门狗将在开机或重连时自动恢复原始拓扑。

---
方案 B 深入：WDA_EXCLUDEFROMCAPTURE 与置顶黑屏遮罩
---

在未安装 IddCx 虚拟驱动的 Windows 系统上，RustDesk 采用基于窗口显示亲和性（Window Display Affinity）的遮罩方案：

1. **置顶无焦点黑屏窗口**：
   在物理屏幕上创建一个全屏黑色无边框窗口，赋予 ``WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TOOLWINDOW`` 扩展样式。
2. **设置抓屏排除属性**：
   调用 Windows 10 2004+ 引入的原生 API ``SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)``。

.. code-block:: rust
   :caption: 抓屏排除黑屏遮罩原理

   // WDA_EXCLUDEFROMCAPTURE = 0x00000011
   // 告知 DWM：在合成最终物理显示器帧时渲染该窗口（显示为全黑）；
   // 但在执行 DXGI Desktop Duplication 或截屏时，直接跳过该窗口层，
   // 暴露出底层的真实应用程序界面！
   unsafe {
       SetWindowDisplayAffinity(black_hwnd, WDA_EXCLUDEFROMCAPTURE);
   }

这一机制使得物理显示器前的旁观者只能看到纯黑遮罩窗口，而远程主控端的 DXGI 捕获引擎却能“穿透”黑屏，完整读取受控端正在运行的应用程序。

---
受控端物理输入阻断（Low-Level Input Hooks）
---

黑屏仅解决了视觉泄露问题，为了防止受控端本地键鼠被误触或恶意操作，RustDesk 在 ``src/privacy_mode/win_input.rs`` 中安装了操作系统全局底层钩子：

* **``WH_KEYBOARD_LL``**: 拦截物理键盘敲击，直接在钩子回调中返回 ``1``（丢弃事件），仅放行包含 ``ENIGO_INPUT_EXTRA_VALUE`` 标记的远程注入按键。
* **``WH_MOUSE_LL``**: 拦截物理鼠标移动与点击，屏蔽现场硬件输入。

***
小结与下章导读
***

至此，**模块 01：操作系统与硬件底层交互原语** 的四大核心基石已全部施工完毕：
* 《01.01 跨平台屏幕像素捕获底层原语与抓屏引擎实现》
* 《01.02 跨平台输入事件注入引擎与多端同步实现》
* 《01.03 低延迟音频捕获、混音与回放子系统》
* 《01.04 IddCx 虚拟显示驱动与隐私屏黑屏机制》

受控端已具备在任何复杂硬件环境（多屏、无头、涉密物理遮蔽）下采集画面、音频并响应输入的能力。

在接下来的 **模块 02：音视频媒体管线与编解码** 中，我们将视野转向多媒体处理的核心引擎：
* **《02.01 帧缓冲对齐、色彩空间转换 (YUV/NV12) 与零拷贝模型》**：深入解析从显存捕获的原始 RGB 像素阵列，如何通过 SIMD 与 GPU Shader 以微秒级延迟完成色彩空间转换与帧缓冲内存对齐。
