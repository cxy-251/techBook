第066章：Cold Start, Warm Start, Resume Path
===========================================

核心知识点
----------

* Cold Start、Warm Start、Hot Resume 的根本差异是系统需要重新建立多少执行状态，而不是用户从哪个入口进入 App。
* Cold Start 通常要求重新创建进程、建立 runtime、装载代码与资源、创建应用对象和首个界面，再提交第一帧。
* Warm Start 可以复用部分进程、代码页、任务状态或缓存，但仍可能需要重新创建 Activity、Scene 或页面对象。
* Hot Resume 主要复用仍在内存中的进程和 UI 对象，成本集中在前台恢复回调、数据刷新和首帧重新提交。
* Android 冷启动常经过 Launcher / system_server → Zygote fork → ActivityThread → Application / Activity → first frame。
* Apple 冷启动可按 process launch → dyld / runtime initialization → UIKit / SwiftUI lifecycle → view creation → first frame 理解。
* TTID 关注首个可见界面，TTFD 关注完整可用状态；首帧前只应保留用户立即需要的最小工作集。
* 启动性能问题必须区分进程创建、代码加载、资源加载、主线程初始化、状态恢复和首帧渲染，不能全部归为“业务代码慢”。

关键路径
--------

用户请求进入 App
→ 判断进程是否存在
→ 不存在：Cold Start
→ 创建进程与安全上下文
→ runtime / dynamic linker 建立执行环境
→ 装载代码、framework 与首屏资源
→ 创建 Application / Activity / Scene
→ 执行最小首屏初始化
→ 提交 first frame
→ 继续异步加载非首屏内容形成 TTFD。

进程存在但目标界面已销毁
→ Warm Start
→ 复用进程和部分缓存
→ 重建页面并恢复 saved state
→ 提交首帧。

进程和界面仍存在
→ Hot Resume
→ 恢复前台状态
→ 刷新必要数据与输入
→ 重新提交可见帧。

概念辨析
--------

``Cold / Warm / Hot`` 与 ``入口来源``：通知、最近任务、桌面图标都可能落入不同启动类型，判断依据是系统实际保留的进程和界面状态。

``TTID`` 与 ``TTFD``：TTID 是第一帧可见时间；TTFD 是核心内容和交互真正准备完成的时间。

``Process creation`` 与 ``App initialization``：前者由系统建立执行容器，后者由 runtime、Framework 和应用代码共同完成。

``Code loading`` 与 ``First-frame work``：代码和 framework 装载是运行前提；数据库迁移、全量索引、远端配置等非首屏工作应尽量推迟。

本章结论
--------

启动路径的本质是补齐缺失状态。性能分析应先判断当前属于 Cold、Warm 还是 Resume，再沿进程创建、runtime、代码资源加载、应用初始化和首帧提交逐层定位，把首帧前工作压缩到用户当前任务所需的最小集合。
