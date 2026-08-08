第110章：Apple AVAudioEngine, Core Audio, Audio Unit, Audio Session
==================================================================

核心知识点
----------

* Apple 音频栈可拆成控制面与数据面：``AVAudioSession`` 表达 App 音频意图，``AVAudioEngine`` 组织信号图，Core Audio / Audio Unit 承担实时处理与设备 I/O。
* ``AVAudioSession`` 通过 category、mode、option、active state 描述播放、录音、通话、Bluetooth、AirPlay、混音与后台行为。
* category 决定基础能力，mode 细化场景，option 调整路由和混音策略；``setActive(true)`` 才是让配置真正参与系统仲裁的关键点。
* ``AVAudioEngine`` 用 input node、player node、effect node、mixer node、output node 组成 signal graph；连接时必须关注 sample rate、channel 和实时预算。
* Core Audio / Audio Unit 的 render callback 受固定 I/O 周期约束，锁、I/O、动态分配和主线程同步都会破坏实时性。
* route change、interruption 和 hardware format change 都可能让已有图失效，App 必须重新读取实际 sample rate、buffer duration 和 current route。
* preferred sample rate / I/O buffer duration 只是偏好请求，实际值由系统和当前硬件 route 决定。

关键路径
--------

控制面：

``App intent → AVAudioSession category / mode / option → setActive → System Audio Policy → Route / Hardware Format``

数据面：

``Input Node → Effect / Mixer Nodes → Output Node → Core Audio / Audio Unit → Driver → Hardware``

一次稳定启动通常遵循：

``Configure Session → Activate Session → Read Actual Route / Format → Build Graph → Prepare → Start Engine``

环境变化后：

``Interruption / Route Change → Stop or Quiesce → Re-read Session State → Rebuild / Reconnect Graph → Resume if allowed``

概念辨析
--------

* **AVAudioSession vs AVAudioEngine**：Session 管系统音频角色和策略；Engine 管 App 侧信号流和节点图。
* **Category vs mode**：category 定义基础录放能力；mode 在此基础上表达 voiceChat、videoChat、measurement 等具体场景。
* **Preferred vs actual format**：App 可以请求偏好，真正运行参数要在 session 激活后读取。
* **Node graph vs hardware route**：节点图描述 App 内部处理关系；route 描述系统选择的真实输入输出设备。
* **Core Audio vs Audio Unit**：Core Audio 是底层音频能力集合；Audio Unit 是其中面向实时处理和 I/O 的组件模型。

本章结论
--------

Apple 音频应按 ``AVAudioSession → AVAudioEngine → Core Audio / Audio Unit → Driver → Hardware`` 阅读。配置成功不等于运行环境固定；route、interruption 和实际硬件格式变化后，App 必须以系统返回状态为准重建实时路径。