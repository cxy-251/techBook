第057章：Dynamic Linking, Shared Libraries, Framework Loading
============================================================

核心知识点
----------

* Dynamic linking 负责把独立编译的共享代码 image 加入当前进程，并把调用点、数据引用和 runtime metadata 连接到实际地址。
* 动态链接器的基本职责包括：加载 image、递归处理依赖、解析符号、执行 relocation、运行 initializer，并返回可调用入口。
* 符号解析回答“名字由哪个 image 提供”，relocation 回答“最终地址写在哪里”，lazy binding 回答“何时完成绑定”。
* Shared library 的价值来自代码复用和只读页共享；成本来自 image 数量、依赖深度、page fault、符号绑定和初始化副作用。
* Android 的 linker namespace、公开 NDK 库与 system/vendor 边界共同限制一个进程能看到哪些 native library。
* Apple 的 dyld、framework、shared cache、code signing 与 library validation 共同构成动态装载边界。
* 动态链接既是 runtime boundary，也是 security boundary：库存在不代表当前进程一定允许加载。

关键路径
--------

通用加载链：

``依赖声明 / dlopen → Dynamic Linker → Namespace / Trust Check → Kernel VM Mapping → Dependency Load → Symbol Resolution → Relocation → Initializer → Callable Entry``

一次首次函数调用可能继续经过：

``调用点 → PLT / Stub → Lazy Bind → GOT / Bind Table 更新 → 真实函数地址``

排查顺序：

#. 确认目标 image 是启动依赖还是运行时按需加载。
#. 确认依赖链中的每个库由 App、系统还是 vendor 提供。
#. 检查架构、路径、namespace、install name、API level 与签名策略。
#. 确认未定义符号是否能在允许搜索的 image 中找到。
#. 启动慢时分析 image 数量、relocation、initializer、page fault 与 dirty memory。

概念辨析
--------

* **Loading 与 Linking**：loading 把 image 映射进地址空间；linking 把引用连接到真实定义与地址。
* **Symbol Resolution 与 Relocation**：前者找到定义，后者修补当前进程中的地址引用。
* **Lazy Binding 与 Load-Time Binding**：前者把部分成本推到首次调用，后者在加载阶段提前完成更多绑定。
* **Shared Library 与 Shared Memory**：共享库可以产生共享代码页，但库中的可写数据并不会天然保持跨进程共享。
* **库文件存在 与 可加载**：还要满足 ABI、namespace、签名、sandbox 和平台版本规则。

本章结论
--------

动态链接把“构建时依赖”变成“运行时可执行关系”。稳定阅读顺序是 ``image → dependency → symbol → relocation → initializer → call``；启动崩溃、符号缺失、私有库依赖和加载性能问题都应沿这条链定位，而不是只看业务函数本身。