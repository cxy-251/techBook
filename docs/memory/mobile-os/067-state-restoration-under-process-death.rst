第067章：State Restoration Under Process Death
==============================================

核心知识点
----------

* Process Death 只表示执行容器被回收；用户任务、导航意图和业务事实必须独立于进程对象保存。
* 状态应拆成 UI State、Navigation State、Domain State、Persistent State 四类，不同类别对应不同生命周期和保存位置。
* UI State 适合保存文本框内容、滚动位置、当前 tab 等轻量界面状态；Navigation State 适合保存 route、稳定 id 和返回路径。
* Domain State 表示笔记、订单、购物车、同步队列等业务事实，应进入 repository、数据库、文件或远端服务，而不是只存在于 ViewModel 或内存对象。
* Android 中 ViewModel 主要解决配置变化；savedInstanceState、SavedStateHandle、rememberSaveable 负责小型恢复令牌；Room、DataStore、文件等负责长期事实。
* Apple 中 Scene session、NSUserActivity、UIKit state restoration 等负责恢复入口和用户意图；Core Data、UserDefaults、文件等负责持久事实。
* Crash、系统回收、用户强退、应用更新、设备重启的恢复语义不同；不能把所有重新启动都按同一种恢复路径处理。
* 跨进程恢复还必须处理数据新鲜度、未提交操作、重复请求和远端冲突，因此关键操作应具备幂等性和明确版本状态。

关键路径
--------

用户执行任务
→ App 持续把关键业务事实写入持久层
→ Framework 保存最小 UI / Navigation 恢复令牌
→ App 进入后台
→ 系统在资源压力下终止进程
→ 进程内对象、线程、单例和缓存全部消失
→ 用户从最近任务、图标、通知或 deep link 返回
→ 系统创建新进程并交付恢复入口
→ App 读取 route / id / Scene session 等最小令牌
→ repository 从数据库、文件或远端读取业务事实
→ 重建 UI 与导航
→ 对未完成操作执行幂等重试或冲突处理
→ 用户继续原任务。

概念辨析
--------

``ViewModel`` 与 ``Persistent state``：ViewModel 只在当前进程内存中有效；进程死亡后必须重新创建，不能承担长期事实保存。

``Saved state`` 与 ``Database``：saved state 适合小型、可序列化的恢复线索；数据库和文件负责业务事实与大容量长期状态。

``UI State`` 与 ``Domain State``：滚动位置、选中项属于界面恢复；笔记正文、订单状态等属于业务事实，可靠性要求更高。

``Process restoration`` 与 ``Data synchronization``：恢复界面只解决本地用户连续性；远端数据可能已经变化，仍需版本、幂等和冲突解决机制。

本章结论
--------

移动 App 必须把 Process Death 当作正常运行路径。稳定架构以最小恢复令牌定位用户任务，以持久层保存业务事实，以幂等和冲突处理恢复未完成操作，从而让进程是否存活不再决定用户数据和任务连续性。
