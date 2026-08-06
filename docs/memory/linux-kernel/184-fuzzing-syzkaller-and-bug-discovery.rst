第184章：Fuzzing、syzkaller 与缺陷发现
=====================================

核心知识点
----------

内核 Fuzzing 探索未规划状态
   Fuzzer 通过生成、变异和组合输入，持续搜索人工测试未覆盖的边界值、调用顺序、对象生命周期与并发窗口。

有效输入必须理解资源关系
   纯随机 Syscall、fd 和指针通常停在浅层校验。深层覆盖需要先创建 File、Socket、Mount、VMA、BPF Map 等资源，再改变参数、顺序和释放时机。

Syscall 序列是一段状态程序
   每个调用既消费已有对象，也可能产生后续调用依赖的新对象。分析 Reproducer 时，应先找资源创建，再找状态转换与最终触发点。

Coverage 只负责引导探索
   KCOV 等机制反馈哪些路径已执行，并帮助保留能产生新覆盖的输入。新 Coverage 不是缺陷证据，Sanitizer、Crash、Hang 或错误行为才是。

syzkaller 依赖声明式接口模型
   Syscall、Struct、Flag、Resource 和方向关系的描述，使生成器能够构造足够合法的程序，并围绕真实对象依赖继续变异。

Reproducer 必须保留触发条件
   ``repro.syz`` 更完整地保留 syzkaller 语义；C Reproducer 更易独立阅读。Commit、Config、Architecture、Sandbox、CPU 数和触发概率都属于复现条件。

修复必须恢复对象协议
   Use-after-free、数据竞争和锁问题应沿分配、发布、访问、移除与释放关系分析，不能靠删除 WARN、改变时序或屏蔽检测器结束问题。

关键路径
--------

Coverage-guided Fuzzing：

::

   接口描述
   → 生成或变异 Program
   → Executor 运行
   → Coverage 反馈
   → Corpus 更新
   → 检测器触发
   → 最小化 Reproducer
   → 修复并固定回归

Reproducer 分析：

::

   固定环境
   → 找资源生产调用
   → 找状态转换
   → 找并发与释放窗口
   → 对齐首个违规栈
   → 重建对象生命周期

概念辨析
--------

* **随机输入与语义化探索**：随机字节常被浅层校验拒绝；语义化 Fuzzing 先建立有效对象，再探索异常组合。
* **Coverage 与 Bug**：Coverage 证明路径执行过；检测器、Crash、Hang 或错误行为才构成缺陷信号。
* **Crash 标题与根因**：标题只用于聚类；根因需要首个违规证据、对象生命周期和稳定复现共同支持。
* **``repro.syz`` 与 C Reproducer**：前者保留更多执行语义，后者更易阅读但可能丢失 Sandbox、并发或注入条件。
* **最后触发调用与最初破坏点**：崩溃位置可能只是暴露早先已经损坏的对象。

本章结论
--------

内核 Fuzzing 的核心，是用资源感知的状态程序和覆盖反馈发现异常路径，再把随机结果压缩成可复现、可解释、可回归的对象级缺陷。
