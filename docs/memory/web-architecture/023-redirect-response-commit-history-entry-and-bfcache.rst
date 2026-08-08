Redirect, Response Commit, History Entry, and BFCache
====================================================

核心知识点
----------

* Redirect 发生在正常 document commit 之前，它可以多次改写最终 URL、请求上下文、origin、缓存路径和服务器入口；真正重要的是最终哪个 response 被 commit。
* Response commit 是导航责任转移点：commit 前浏览器仍可 redirect、取消、下载或保留旧 document；commit 后新 document 开始拥有页面生命周期和执行环境。
* History entry 不只保存 URL，还可关联 History API state、scroll restoration、document state 和浏览器选择保存的表单/用户状态。
* ``pushState``/``replaceState`` 创建或修改同文档 history entry；用户 Back/Forward 时应用通过 ``popstate`` 恢复 route state。
* BFCache 保存的是被冻结的完整页面运行时，包括 Document、DOM、JavaScript heap 与大量 UI 状态；HTTP cache 保存的是网络响应副本，二者完全不同。
* 页面进入 BFCache 时不应按“彻底销毁”处理；``pagehide``/``pageshow`` 的 ``persisted`` 可帮助区分保存与恢复路径。
* 从 BFCache 恢复很快，但内存中的业务数据可能已经过期；恢复后应按状态所有权重新验证服务器事实、认证状态和实时连接。
* ``unload``、长期占用资源或其他浏览器特定条件可能降低 BFCache eligibility；应用应依赖可恢复生命周期，而不是假设返回一定重新加载或一定命中 BFCache。

关键路径
--------

Redirect 到最终页面：

``Navigation Request → Redirect Response → Location → New Request → Final Response → Commit → Active Document → History Entry``

History traversal：

``Back/Forward → Target History Entry → BFCache hit ? restore frozen Document : reload/recreate → restore URL/state/scroll → freshness check``

BFCache 生命周期：

``Active Document → pagehide(persisted=true) → frozen/preserved → pageshow(persisted=true) → resume ephemeral work + revalidate durable facts``

概念辨析
--------

* **Redirect vs Commit**：redirect 改写尚未提交的导航；commit 才让响应成为当前页面。
* **History Entry vs URL**：entry 是可遍历的页面位置记录，URL 只是其中一个核心字段。
* **History API state vs Server State**：History state 用于同文档导航恢复，不应成为订单、权限等权威业务事实。
* **BFCache vs HTTP Cache**：BFCache 保存完整运行中的页面快照；HTTP cache 保存 response representation。
* **BFCache Restore vs Reload**：restore 延续旧 document 和内存；reload 创建新 document 并重新执行启动路径。

本章结论
--------

浏览器导航不是“请求 URL 后显示 HTML”的一次动作，而是 ``redirect → commit → history entry → traversal/recovery`` 的状态机。设计路由和返回体验时，必须同时支持重新加载、同文档 history 恢复和 BFCache restore，并在恢复后重新校验那些不属于浏览器页面内存所有的外部事实。