======================================================================
01.02 跨平台输入事件注入引擎与多端同步实现
======================================================================

.. note:: 前置背景与上下文承接
   在前一章《01.01 跨平台屏幕像素捕获底层原语与抓屏引擎实现》中，我们解剖了从物理显存与操作系统窗口组合器中高效捕获画面的完整路径。然而，远程控制的另一半核心生命线是**从远端客户端采集的用户输入（键盘按键、鼠标位移、点击滚轮、触控手势），如何以毫秒级延迟、无丢失、无死锁地注入到受控端操作系统的输入队列中**。本章将深入剖析 RustDesk 在 Windows、macOS 与 Linux（X11/Wayland）异构平台下的输入仿真机制，以及其在 ``libs/enigo`` 与 ``src/server/input_service.rs`` 中实现的复杂键盘映射模式、LED 状态锁同步与按键防卡死容灾模型。

***
操作系统输入子系统与事件队列模型
***

现代操作系统的输入架构在内核层与用户空间之间建立了严格的抽象屏障。物理硬件（USB HID 设备、PS/2 控制器、I2C 触控板）通过硬件中断向内核输入驱动提交原始扫描码（Scancode / Report Descriptor），内核随后将其封装为事件投递至窗口系统：

* **Windows**: 原始输入（Raw Input）经过 Windows 子系统内核模块（``win32k.sys`` / ``win32kbase.sys``），转换为 Windows 消息（``WM_KEYDOWN``、``WM_MOUSEMOVE`` 等），推入目标线程的系统消息队列（System Message Queue）。
* **macOS**: I/O Kit 处理底层 HID 报告，通过 WindowServer 将事件打包为 ``CGEventRef``，沿着事件链（Event Tap Pipeline）逐级向下分发至前台应用程序的 ``NSApplication`` 事件循环。
* **Linux**: Linux 内核 ``evdev`` 子系统在 ``/dev/input/event*`` 暴露标准化事件结构；X11 通过 X Server 进行事件路由与全局分发，而 Wayland 则基于安全沙箱隔离原则，仅由 Wayland Compositor（Mutter/KWin）将焦点窗口的事件通过私有 Wayland 协议传递给客户端。

.. list-table:: 三大操作系统输入注入原语对比
   :widths: 18 25 32 25
   :header-rows: 1

   * - 平台
     - 注入核心 API
     - 驱动/权限层级
     - 特殊限制与安全边界
   * - **Windows**
     - ``SendInput`` / ``SAS (Ctrl+Alt+Del)``
     - 用户态 Win32 子系统 / Session 隔离
     - UIPI 隔离（低权限无法注入高权限窗口）、安全桌面（Winlogon/UAC）需服务提权
   * - **macOS**
     - ``CGEventPost`` / ``rdev::VirtualInput``
     - CoreGraphics / 辅助功能权限 (TCC)
     - 必须授权 Accessibility 权限；必须在 GUI 主线程分发以防崩溃
   * - **Linux (X11)**
     - ``XTestFakeKeyEvent`` / ``XTest`` 扩展
     - X11 协议扩展 / X Server 权限
     - 仅限 X11 会话，全屏游戏可能绕过 X11 直接读取 evdev
   * - **Linux (Wayland)**
     - ``/dev/uinput`` 内核模块 / RDP Portal
     - 内核级虚拟驱动 (``root`` 或 ``input`` 组)
     - 合成器禁止无授权跨进程注入；非 ASCII 字符需剪贴板协议桥接

---
Windows 平台：SendInput 与虚拟桌面坐标变换
---

在 Windows 端，RustDesk 在 ``libs/enigo/src/win/win_impl.rs`` 中调用 Win32 原生 API ``SendInput``，它允许单次原子提交一组 ``INPUT`` 结构体（支持 ``INPUT_MOUSE`` 与 ``INPUT_KEYBOARD``）。

鼠标绝对坐标与虚拟多屏归一化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当受控端存在多个物理显示器或高 DPI 缩放时，鼠标绝对坐标必须基于 Windows 虚拟屏幕（Virtual Screen）进行归一化转换。Windows API 规定绝对坐标范围为 $[0, 65535]$：

.. math::

   X_{	ext{norm}} = \frac{(X_{	ext{target}} - 	ext{SM\_XVIRTUALSCREEN}) 	imes 65535}{	ext{SM\_CXVIRTUALSCREEN}}

.. math::

   Y_{	ext{norm}} = \frac{(Y_{	ext{target}} - 	ext{SM\_YVIRTUALSCREEN}) 	imes 65535}{	ext{SM\_CYVIRTUALSCREEN}}

.. code-block:: rust
   :caption: Windows 鼠标事件注入实现（libs/enigo/src/win/win_impl.rs）

   pub const ENIGO_INPUT_EXTRA_VALUE: ULONG_PTR = 100;

   fn mouse_event(flags: u32, data: u32, dx: i32, dy: i32) -> DWORD {
       let mut u = INPUT_u::default();
       unsafe {
           *u.mi_mut() = MOUSEINPUT {
               dx,
               dy,
               mouseData: data,
               dwFlags: flags,
               time: 0,
               dwExtraInfo: ENIGO_INPUT_EXTRA_VALUE, // 用于输入回环过滤标记
           };
       }
       let mut input = INPUT {
           type_: INPUT_MOUSE,
           u,
       };
       unsafe { SendInput(1, &mut input as LPINPUT, size_of::<INPUT>() as c_int) }
   }

扫描码与虚拟键码（VK）的动态映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为应对远端与受控端不同键盘布局（如德语 QWERTZ 与美式 QWERTY）的差异，RustDesk 动态获取当前前台焦点窗口的线程键盘布局句柄 ``HKL``：

.. code-block:: rust
   :caption: 键盘布局感知与扫描码解析

   fn keybd_event(mut flags: u32, vk: u16, scan: u16) -> DWORD {
       let mut scan = scan;
       unsafe {
           if scan == 0 {
               if LAYOUT.is_null() {
                   let current_window_thread_id =
                       GetWindowThreadProcessId(GetForegroundWindow(), std::ptr::null_mut());
                   LAYOUT = GetKeyboardLayout(current_window_thread_id);
               }
               // 根据目标窗口的键盘布局反查硬件扫描码
               scan = MapVirtualKeyExW(vk as _, 0, LAYOUT) as _;
           }
       }
       // 处理扩展按键前缀 (0xE0 / 0xE1)
       if flags & KEYEVENTF_UNICODE == 0 {
           if scan >> 8 == 0xE0 || scan >> 8 == 0xE1 {
               flags |= winapi::um::winuser::KEYEVENTF_EXTENDEDKEY;
           }
       }
       // 组装 KEYBDINPUT 并提交 SendInput...
   }

---
macOS 平台：CoreGraphics 事件管线与主线程约束
---

macOS 拥有极度严格的窗口安全隔离与辅助功能权限检查（TCC - Transparency, Consent, and Control）。RustDesk 在 macOS 端通过 ``rdev::VirtualInput`` 与 CoreGraphics ``CGEventPost`` 实现事件注入。

主线程分发与时序补偿
~~~~~~~~~~~~~~~~~~~~

在 macOS 10.15 Catalina 及更高版本中，非主线程直接调用 CoreGraphics 事件注入 API 可能导致 WindowServer 客户端连接断开甚至整个守护进程异常退出。RustDesk 在 ``src/server/input_service.rs`` 中通过 Grand Central Dispatch (GCD) 队列强制将所有输入操作排队至主线程：

.. code-block:: rust
   :caption: macOS 主线程事件队列与按键延迟时序补偿

   #[cfg(target_os = "macos")]
   lazy_static::lazy_static! {
       static ref QUEUE: Queue = Queue::main();
   }

   #[inline]
   #[cfg(target_os = "macos")]
   pub fn handle_key(evt: &KeyEvent) {
       let evt = evt.clone();
       QUEUE.exec_async(move || handle_key_(&evt));
       
       // macOS 输入时序保护：在高频输入时补偿 12ms 延时
       // 防止 launchctl 守护进程环境下按键被窗口系统粘滞或丢失修饰键
       key_sleep();
   }

   #[inline]
   #[cfg(target_os = "macos")]
   fn key_sleep() {
       let now = Instant::now();
       while now.elapsed() < Duration::from_millis(12) {
           std::thread::sleep(Duration::from_millis(1));
       }
   }

---
Linux 平台：X11 与 Wayland ``/dev/uinput`` 虚拟内核设备
---

Linux 平台的输入注入在不同显示架构下有着本质分水岭：

1. **X11 路径**：直接使用 ``XTestFakeKeyEvent`` 向 X Display 发送事件，开销极小且通用性强。
2. **Wayland 路径**：Wayland Compositor 彻底废弃了 XTest。RustDesk 采用双模架构：
   * **系统服务模式 (Root / Service)**：通过 Linux 内核模块 ``/dev/uinput`` 直接在内核层动态注册一个全新的虚拟硬件键盘（``UInputKeyboard``）和虚拟鼠标（``UInputMouse``）。
   * **桌面会话模式 (Desktop / Server)**：通过 XDG Desktop Portal 的 RemoteDesktop 接口进行注入代理。

.. code-block:: rust
   :caption: Wayland uinput 虚拟设备初始化与分辨率同步

   #[cfg(target_os = "linux")]
   pub async fn setup_uinput(minx: i32, maxx: i32, miny: i32, maxy: i32) -> ResultType<()> {
       // 向 /dev/uinput 写入绝对坐标轴 (ABS_X, ABS_Y) 物理分辨率边界
       set_uinput_resolution(minx, maxx, miny, maxy).await?;

       let keyboard = super::uinput::client::UInputKeyboard::new().await?;
       let mouse = super::uinput::client::UInputMouse::new().await?;

       let mut en = ENIGO.lock().unwrap();
       en.set_is_x11(false);
       en.set_custom_keyboard(Box::new(keyboard));
       en.set_custom_mouse(Box::new(mouse));
       Ok(())
   }

.. note:: Wayland 下非 ASCII 字符的“剪贴板穿透注入”
   由于 Linux ``uinput`` 仅能模拟物理按键扫描码（evdev keycodes），当用户输入中文字符、Emoji 或复杂 Unicode 标量时，内核虚拟键盘无法直接合成无扫描码对应的字符。RustDesk 巧妙地采用了**快速剪贴板桥接（Shift+Insert）机制**：将目标文本瞬间写入本地主机剪贴板，随后通过虚拟键盘触发 ``Shift + Insert`` 完成原子级粘贴，并在 20ms 内完成事件确认，从而在 Wayland 环境下完美解决了全字符集输入难题。

---
RustDesk 核心输入服务架构 (``src/server/input_service.rs``)
---

在服务端运行时，``input_service.rs`` 承担了从网络反序列化输入报文到本地调度的中枢职责。其核心架构由以下三大状态机与容灾模块构成：

1. 三大键盘映射模式架构
~~~~~~~~~~~~~~~~~~~~~~~~

RustDesk 提供了三种适应不同网络与业务场景的键盘映射模式（``KeyboardMode``）：

* **``KeyboardMode::Legacy``（字符/传统模式）**：
  将输入视为字符流。在注入字符前自动释放 Shift 等修饰键（避免把已由客户端处理好的小写变大写），适合跨不同物理键盘布局的高精度文本编辑。
* **``KeyboardMode::Map``（物理键位映射模式）**：
  直接传递物理按键的原始扫描码（Scancode / KeyCode）。不管本地布局如何，严格还原按键的物理位置，专为 **3D 游戏（WASD 移动）与快捷键密集型专业软件** 优化。
* **``KeyboardMode::Translate``（翻译模式）**：
  由客户端计算好键位与序列，服务端结合本地布局与 Unicode 注入进行自适应混合分发。

2. LED 与锁定键（CapsLock / NumLock）状态同步机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当远端客户端与受控端的 CapsLock / NumLock 硬件状态不一致时，若直接输入可能导致大小写完全反转。RustDesk 使用 RAII 模式的 ``LockModesHandler`` 进行无感对齐：

.. code-block:: rust
   :caption: RAII 模式的 LockModesHandler 状态锁守卫

   #[cfg(any(target_os = "windows", target_os = "linux"))]
   struct LockModesHandler {
       caps_lock_changed: bool,
       num_lock_changed: bool,
   }

   impl LockModesHandler {
       fn new(key_event: &KeyEvent, is_numpad_key: bool) -> Self {
           let mut en = ENIGO.lock().unwrap();
           let event_caps = Self::is_modifier_enabled(key_event, ControlKey::CapsLock);
           let local_caps = en.get_key_state(enigo::Key::CapsLock);
           let caps_lock_changed = event_caps != local_caps;
           
           // 若状态不一致，临时模拟一次 CapsLock 点击以修正受控端 LED 状态
           if caps_lock_changed {
               en.key_click(enigo::Key::CapsLock);
           }
           // 同样的逻辑对 NumLock 执行同步...
           Self { caps_lock_changed, num_lock_changed }
       }
   }

   // 当按键事件执行完毕退出作用域时，Drop trait 自动清理并恢复原始状态
   #[cfg(any(target_os = "windows", target_os = "linux"))]
   impl Drop for LockModesHandler {
       fn drop(&mut self) {
           let mut en = ENIGO.lock().unwrap();
           if self.caps_lock_changed {
               en.key_click(enigo::Key::CapsLock);
           }
           if self.num_lock_changed {
               en.key_click(enigo::Key::NumLock);
           }
       }
   }

3. 按键防卡死与看门狗容灾机制 (``fix_key_down_timeout``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在远程桌面连接中，若远端用户按住 ``Ctrl`` 或 ``Alt`` 时发生网络瞬断、崩溃或异常关闭，受控端将永远无法收到 ``KeyUp`` 释放事件，导致受控端主机的键盘陷入“按键粘滞卡死”状态。

RustDesk 在底层建立了全局按键跟踪哈希表与定时看门狗：

.. code-block:: rust
   :caption: 按键超时与看门狗清理机制

   static ref KEYS_DOWN: Arc<Mutex<HashMap<KeysDown, Instant>>> = Default::default();

   pub fn fix_key_down_timeout_loop() {
       std::thread::spawn(move || loop {
           std::thread::sleep(std::time::Duration::from_millis(10_000));
           // 定期扫描：凡是按下持续超过 360 秒未释放的按键，强制发送 KeyUp 并从表中剔除
           fix_key_down_timeout(false);
       });
       
       // 捕获 Ctrl+C 或进程异常退出信号，在终端销毁前释放全部被按下的修饰键
       if let Err(err) = ctrlc::set_handler(move || {
           fix_key_down_timeout_at_exit();
           std::process::exit(0);
       }) {
           log::error!("Failed to set Ctrl-C handler: {}", err);
       }
   }

4. 相对鼠标位移模式 (``MOUSE_TYPE_MOVE_RELATIVE``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

针对第一人称 3D 游戏与 CAD 建模场景，光标被锁定在屏幕中心，传统绝对坐标移动会导致视角无法连续旋转。RustDesk 实现了独立的相对位移链路：

* 接收 $(\Delta x, \Delta y)$ 增量向量，并在服务端进行安全钳制（限制在 $[-10000, 10000]$ 范围内，防止恶意构造畸变数值引发驱动溢出）。
* 激活相对移动模式时，自动关闭白板标注与光标位置的额外广播，消除光标位置冲突抖动。

***
小结与下章导读
***

本章全面解构了 RustDesk 跨平台输入注入引擎的底层实现：
* 分析了 Windows ``SendInput``、macOS ``CGEvent``（主线程队列与时序约束）以及 Linux（X11 与 Wayland ``/dev/uinput``）的差异与实现细节。
* 剖析了 ``input_service.rs`` 中的 Legacy / Map / Translate 键盘模式、LED 状态锁同步、Wayland 剪贴板文本注入桥接以及防按键卡死看门狗。

在下一节中，我们将探索音频子系统的低延迟管道：
* **《01.03 低延迟音频捕获、混音与回放子系统》**：剖析 Windows WASAPI（Loopback 抓取）、macOS CoreAudio 及 Linux ALSA/PulseAudio/PipeWire 如何实现声画同步与毫秒级音频推流。
