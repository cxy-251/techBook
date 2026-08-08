第112章：Low-Latency Audio and Real-Time Constraint
===================================================

核心知识点
----------

* 低延迟音频关注的是触发、采集、处理、播放之间的端到端时间，而不是某个 API 单独执行多快。
* 典型目标包括 output latency、input latency 和 round-trip latency；虚拟乐器、实时监听、游戏反馈、VoIP 对不同链路敏感程度不同。
* Buffer size、callback period 和 scheduling priority 构成实时路径的核心取舍：buffer 越小延迟越低，同时越容易暴露调度抖动。
* Fast path 通过格式匹配、短 buffer 周期、较少中间处理和高优先级线程缩短延迟；普通路径换取更强的混音、效果和兼容性。
* Real-time callback 必须短、稳定、可预测：避免锁等待、磁盘 I/O、日志 flush、网络访问、动态内存分配和同步 IPC。
* 主线程负责 UI 和控制，实时音频线程负责固定 deadline 的数据处理；两者应通过无锁 ring buffer、原子参数或预分配 command queue 交换状态。
* Bluetooth、USB 和内置音频的路径长度不同；Bluetooth 通常额外引入编码、无线调度和设备端 buffer，因此低延迟能力不能只看 App buffer。

关键路径
--------

触发到发声：

``Touch / MIDI Event → App State → Audio Callback → Mixer / HAL → Driver / Device → Audible Output``

实时监听：

``Microphone → Input Buffer → App DSP → Output Buffer → Mixer / HAL → Headphone``

总延迟可近似拆成：

``Input / Trigger Entry + App Processing + System Queueing + Device I/O``

实时线程原则：

``Preload / Preallocate → Lock-Free Parameter Transfer → Fixed-Time DSP → Fill Buffer Before Deadline``

概念辨析
--------

* **Low latency vs high throughput**：低延迟追求少排队和短周期；高吞吐可以接受更大批量和更深 buffer。
* **Fast path vs normal path**：Fast path 依赖更严格条件；normal path 提供更强兼容性和处理能力。
* **Average performance vs real-time guarantee**：平均很快不能避免偶发 callback 超时，实时路径更关心最坏情况和抖动。
* **Buffering vs latency**：buffer 是稳定性储备，也是额外等待时间来源。
* **Main thread vs real-time thread**：主线程负责交互和状态；实时线程必须隔离不可预测工作。

本章结论
--------

低延迟音频的本质是 deadline 管理。真正有效的优化顺序是先缩短并稳定 callback 路径，再匹配设备原生格式和 buffer 周期，最后根据实际 route 判断是否能进入 fast path；不能依靠单次性能测试或一个“低延迟”开关推断整条链路。