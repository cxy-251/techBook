第093章：Route State, Form State, and Data State Coordination
============================================================

核心知识点
----------

* Route state、form state、data state 分别回答“用户在哪里”“用户正准备做什么”“当前能相信什么远端事实”，三者 owner、生命周期和恢复方式不同。
* Route state 至少包括 pathname、params、search params、matched route、layout segment 与 history entry，是 UI、数据和权限上下文的基础。
* Form state 是尚未成为服务端事实的用户意图，包括草稿、dirty、validation、pending submit、action error 与上传进度。
* Data state 是服务器事实或其缓存副本，需要明确来源、cache key、新鲜度、刷新状态、权限和失效规则。
* Navigation 会中断当前 route 内的读取、提交、校验与上传；每个 pending work 都必须定义取消、继续、转移归属或结果丢弃策略。
* 状态结果提交 UI 前必须核对当前 route key，避免旧表单错误、旧数据响应或旧 mutation 状态覆盖新页面。

关键路径
--------

``URL/History → Route Match → Route Context → Form Draft + Data Snapshot → Submit/Refresh → Navigation Check → UI Commit/Recovery``

* 对 ``/projects/42/orders/9001/edit?tab=items``，``projectId``、``orderId`` 和 ``tab`` 构成当前 route context。
* 数据查询 key 至少覆盖 project/order/tab，以及会改变响应的 tenant、locale、auth/permission 等维度。
* 表单草稿绑定当前 order route key；用户切到订单 ``9002`` 后，``9001`` 的字段错误和提交结果不能继续写入当前表单。
* 保存动作进入 pending 后，服务端事实仍与草稿区分；成功后 revalidate/update cache，失败后保留草稿并显示可定位错误。
* 读请求离开 route 后可以 abort，或允许完成但只能写回原 cache key；写请求一旦已提交服务器，客户端取消界面不等于服务端事务被撤销。
* 导航前检查未提交草稿、pending mutation 和长任务，按产品语义决定阻止离开、提示、后台继续或保存草稿。

概念辨析
--------

* **Route state vs form state**：route state 描述公开导航位置；form state 描述当前 route 内尚未确认的用户意图。
* **Form draft vs server truth**：草稿可以立即变化并失败恢复；server truth 只有远端写入确认后才改变。
* **Data state vs cache state**：server data 是权威来源；query/browser/framework cache 是带新鲜度和生命周期的副本。
* **Abort read vs cancel write**：读取通常可安全取消；写入已到 server 后必须依靠幂等、事务和结果协调，而不能假设前端 abort 会撤销业务动作。
* **UI unmount vs work ownership**：组件卸载只说明可见 owner 消失，不代表网络、server action 或缓存工作自动停止。

本章结论
--------

Router 应被看成状态协调器，而不是单纯的页面选择器。稳定导航要求 route、form、data 各自拥有清晰的 key、生命周期和恢复责任；所有异步结果在 commit 前都要确认仍属于当前 route。只要草稿、远端事实、缓存副本和导航位置不混为一体，快速切页、返回、提交失败和后台刷新就能保持一致，而不会出现“URL 已经变了，旧状态还留在屏幕上”的典型架构错误。
