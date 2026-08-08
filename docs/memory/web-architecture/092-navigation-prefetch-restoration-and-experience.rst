第092章：Navigation Prefetch, Restoration, and Experience
========================================================

核心知识点
----------

* 导航体验不仅是“跳得快”，还包括预取命中、URL/History 正确、pending 反馈、scroll/focus 恢复、错误路径与动画语义。
* Prefetch 把“可能发生的未来导航”变成提前执行的低优先级工作；它会真实消耗网络、服务器、缓存和浏览器资源。
* Prefetch 只适合无副作用的读取路径。登出、支付、领取、锁库存、语言切换等会改变状态的动作不能因为概率意图被提前执行。
* 预取策略应同时考虑用户意图强度和成本：viewport 是弱信号，hover/focus 更强，真实 click 才是确认意图。
* Scroll restoration 属于导航正确性，尤其是列表→详情→返回、长文档与虚拟列表场景；位置应绑定 history/route context。
* Focus restoration 属于可访问性和键盘导航正确性，路由变化后焦点应进入当前页面有意义的语义区域。
* View transition/动画只能服务空间连续性和状态反馈，还必须尊重 reduced-motion、输入响应与失败路径。

关键路径
--------

``Intent Signal → Optional Prefetch → Click Navigation → Route/Data Commit → Scroll Restore → Focus Restore → User Feedback``

* 链接进入 viewport 时只预取低成本 route shell/chunk；hover 或 keyboard focus 后再考虑公开、可缓存的数据。
* 检查 ``saveData``、网络条件、资源体积、auth context、cache scope 与服务器副作用，设置并发上限、去重和过期时间。
* 真正点击后以当前 route/cache 判断提前工作是否可复用；私有或易变数据仍应在真实导航中重新确认。
* 返回历史 entry 时，scroll 状态应与具体 pathname/query/entry 绑定，等待关键内容高度稳定后再恢复。
* 虚拟列表优先恢复“语义对象/列表项”而非仅恢复像素坐标，否则数据变化后相同 ``scrollY`` 可能对应错误内容。
* 路由提交后把焦点移动到主标题、main region 或明确目标，避免键盘用户仍停留在已经卸载的旧链接上。

概念辨析
--------

* **Prefetch vs navigation**：prefetch 是概率性提前读取；navigation 是用户确认后的状态转换。
* **Prefetch vs prerender**：prefetch 主要准备资源/响应；prerender 可能提前创建更完整页面，成本和隐私要求更高。
* **Cache hit vs freshness**：提前命中只能说明已有副本，不说明个性化、库存、权限等数据仍然有效。
* **Scroll restoration vs scroll-to-top**：返回历史页面通常需要恢复上下文；进入全新页面通常更接近顶部或显式锚点。
* **Focus restoration vs visual transition**：焦点解决可操作位置和辅助技术上下文；动画解决视觉连续性，两者职责不同。

本章结论
--------

导航体验是提前工作、真实导航、历史恢复和可访问性反馈的组合。Prefetch 必须服从纯读取、成本和缓存边界；Back/Forward 必须恢复合理 scroll 与 focus；动画不能牺牲输入响应或 reduced-motion。好的导航系统不是单纯减少毫秒，而是让用户始终知道自己在哪里、系统正在做什么、返回后还能继续原任务。
