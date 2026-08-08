第061章：Web Worker, Shared Worker, Worklet, and Off-Main-Thread Execution
========================================================================

核心知识点
----------

* Worker 家族的核心目标是把部分 JavaScript 工作移出页面主线程，降低长任务、输入延迟和渲染争用；代价是通信、复制、生命周期和调试复杂度上升。
* Dedicated Worker 属于单个创建方，适合 CPU 密集、输入输出明确、无需直接操作 DOM 的任务，如解析、索引、压缩、计算和部分本地数据处理。
* Worker 不能直接访问页面 DOM。主线程仍拥有 document、可见 UI、焦点、可访问性和最终交互反馈；worker 只拥有被交付的计算状态和数据副本。
* ``postMessage()`` 定义线程边界。默认使用 structured clone；大块 ``ArrayBuffer`` 等对象可通过 transferable 转移所有权，减少复制成本。
* 消息协议应显式包含 ``type``、``requestId``、``payload``、``error``、可选 ``version``；异步结果必须防止旧请求覆盖新 UI。
* ``terminate()`` 是粗粒度结束整个 worker；复杂任务更适合用 cancel message、request id 或分块计算建立细粒度取消路径。
* Shared Worker 可以让同源多个 browsing context 共享一个协调 runtime，适合跨 tab 的连接、索引或状态协调；它不是持久服务器，生命周期仍由浏览器和连接页面决定。
* Worklet 面向浏览器特定低延迟管线，如 AudioWorklet 等。它通常运行在更严格环境中，代码应短、确定、避免阻塞，不应承担通用应用状态管理。
* ``SharedArrayBuffer`` / ``Atomics`` 引入共享内存和并发协议，需要 cross-origin isolation 等安全前提；普通业务优先使用 clone/transfer 的明确所有权模型。

关键路径
--------

Dedicated Worker：

::

   User action
     → Main thread captures intent
     → postMessage(requestId, payload)
     → Worker computes
     → postMessage(result / error)
     → Main validates requestId
     → DOM / UI update

大数据所有权转移：

::

   Main owns ArrayBuffer
     → postMessage(..., [buffer])
     → sender buffer detached
     → Worker owns buffer
     → process
     → return compact result or transfer output

Shared Worker：

::

   Tab A ─┐
          ├→ MessagePort → Shared Worker → shared coordination
   Tab B ─┘

Worklet：

::

   Main/UI state
     → configure worklet
     → browser-specific render/audio pipeline
     → high-frequency constrained callback
     → output consumed by host pipeline

概念辨析
--------

* Worker 与异步 Promise：Promise continuation 仍可能在主线程执行；Worker 才提供独立执行上下文。
* Worker 与 DOM：Worker 可做计算和部分 Web API 调用，但页面结构、焦点和渲染提交仍归主线程。
* structured clone 与 transfer：前者复制可克隆数据，后者转移资源所有权并让发送方失去原资源。
* Dedicated Worker 与 Shared Worker：前者天然绑定单个创建方，后者作为多个同源 context 的共享协调点。
* Worker 与 Worklet：Worker 是通用后台执行环境；Worklet 是嵌入音频、渲染等特定浏览器管线的受限执行点。
* 并行与更快：任务很短或消息很大时，启动、序列化和同步成本可能抵消并行收益。

本章结论
--------

迁移工作前先确认主线程瓶颈，再判断任务是否依赖 DOM、输入输出多大、生命周期多长。稳定模型是 ``Main owns user-visible state → Worker owns isolated work → message protocol returns result/error/cancel``。Worker 优化的关键不是“多线程”，而是建立清楚的执行与数据所有权边界，让高成本计算离开主线程又不破坏 UI 状态一致性。