Page Lifecycle, Visibility, Freeze, Resume, and Recovery Paths
=============================================================

核心知识点
----------

* 页面生命周期应视为 runtime state machine：同一 tab 中的页面可能 active、hidden、frozen、BFCache-preserved、discarded、terminated 或重新创建。
* ``visibilitychange`` 是跨浏览器较稳定的可见性信号；hidden 页面可能降低 timer、animation 和后台任务调度，不应依赖精确后台执行时间。
* Freeze 表示浏览器保留页面内存但暂停大量执行；Resume 后 wall-clock 已经变化，timer、网络、实时连接和缓存事实都可能过期。
* BFCache restore 延续旧 document 与 JS heap；discard/reload 则丢失内存并创建新 document，两条“回到页面”路径需要不同恢复策略。
* 浏览器拥有是否冻结、保存或丢弃页面的最终控制；应用只能观察部分信号并准备可恢复状态。
* 状态必须分层：URL、cookie/session、server/database state 可跨 document 恢复；未提交草稿、滚动、焦点和临时 UI state 要按价值选择 memory、sessionStorage 或可重建模型。
* 页面重新 visible/resume/pageshow 后，应重建 realtime channel、取消/替换陈旧请求、重新验证服务器事实，并避免重复提交已完成 mutation。
* ``beforeunload``/``unload`` 不适合作为可靠持久化边界；关键用户数据应在正常交互过程中及时保存，而不是寄希望于页面终止瞬间。

关键路径
--------

普通后台切换：

``Active → visibilitychange(hidden) → reduce/pause nonessential work → visibilitychange(visible) → revalidate facts → resume work``

冻结恢复：

``Hidden → Freeze → execution paused → Resume → reconnect/revalidate → UI continues``

BFCache 与丢弃分支：

``Leave Page → pagehide → BFCache preserve ? pageshow(persisted) : document destroyed``

``Background Memory Pressure → Discard → User Returns → New Navigation/Document → restore from URL/storage/server``

概念辨析
--------

* **Hidden vs Frozen**：hidden 主要表示不可见，JavaScript 仍可能运行但受限；frozen 表示执行被更强地暂停。
* **Freeze vs BFCache**：freeze 是后台资源管理状态；BFCache 是历史导航保存完整页面以便前进后退恢复的机制。
* **BFCache Restore vs Reload**：restore 保留原内存；reload 重新创建 document，应用启动代码会再次执行。
* **Timer 时间 vs 真实时间**：后台/冻结会推迟 callback；恢复后应比较时间戳和服务器版本，而不是假设 timer 按时执行。
* **UI State vs Durable State**：滚动、焦点和组件展开状态属于页面体验；订单、权限、余额等事实必须回到服务端权威边界确认。

本章结论
--------

页面并非从加载到关闭一直连续执行。可靠 Web 应用必须把 ``visible/hidden → freeze/resume → BFCache restore → discard/reload`` 都当作正常路径：在进入后台时降低工作量，在恢复时重新验证外部事实，在内存丢失后能从 URL、存储和服务器重建页面，并始终按状态所有权决定什么可以沿用、什么必须刷新。