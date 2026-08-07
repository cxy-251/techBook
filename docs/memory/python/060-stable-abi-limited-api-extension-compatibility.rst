第060章：Stable ABI, Limited API, and Extension Compatibility
============================================================

核心知识点
----------

* 扩展兼容性必须区分 API 与 ABI：API 是源码能调用哪些名字和结构；ABI 是编译后二进制依赖哪些符号、布局和调用约定。
* 完整 CPython C API 通常允许访问更多版本专属能力，产物也更容易绑定某个 CPython 小版本。
* Limited API 是公开 C API 的受限子集，目标是减少扩展对 CPython 内部结构的直接依赖。
* ``Py_LIMITED_API`` 必须在包含 ``Python.h`` 前定义；它决定编译期头文件暴露哪些 API。
* Stable ABI 是二进制层面的稳定契约；符合 Stable ABI 的扩展可以在同一平台上跨多个 CPython 3 小版本加载。
* ``abi3`` wheel 表达的是 CPython Stable ABI 目标；例如 ``cp310-abi3`` 表示最低从 CPython 3.10 起使用相应 Stable ABI。
* Limited API 与 Stable ABI 职责不同：前者收窄编译期可见面，后者约束二进制加载面。
* 最低 Python 版本决定可用 Limited API 集合；使用更晚才进入 Limited API 的函数，就必须提高最低版本。
* wheel tag 只表达安装器匹配声明，不自动证明二进制真的只使用了 Stable ABI。
* 公开 API、Limited API、Unstable API、private/internal API 的稳定性级别不同；``_Py...`` 和 internal header 会显著增加版本耦合。
* 直接读取对象内部字段、使用依赖布局的宏、包含 ``internal/pycore_*.h`` 都会把扩展绑定到 CPython 当前实现。
* Limited API 往往牺牲一部分直接字段访问或宏级性能，以换取 CPython 内部结构可演进和跨版本二进制复用。
* Stable ABI 只解决一部分兼容问题；语言语义、标准库行为、平台 ABI、编译器、依赖库和扩展自身状态仍需要测试。
* 完整 ABI 路线适合需要最新 CPython internals、极致性能或版本专属能力的扩展；abi3 路线适合 API 边界稳定、希望减少 wheel 数量的扩展。
* 发布前必须同时验证头文件使用面、链接符号、wheel tag 和目标 Python 版本运行测试。

关键路径
--------

源码到运行时：

::

    C source
      -> Python.h exposure
      -> API surface
      -> compiler/linker
      -> binary symbols + ABI dependencies
      -> extension .so/.pyd
      -> wheel tag
      -> installer match
      -> CPython import

Limited API 路线：

::

    define Py_LIMITED_API=min_version
      -> include Python.h
      -> only Limited API visible
      -> build extension
      -> inspect binary dependencies
      -> package as cp3xx-abi3
      -> test on every supported Python version

完整 CPython ABI 路线：

::

    full Python.h / version-specific API
      -> build for CPython X.Y
      -> cpXY-cpXY wheel
      -> repeat for each supported minor version

内部耦合风险：

::

    internal header / _Py* / object layout macro
      -> implementation coupling
      -> CPython minor-version change
      -> compile failure / load failure / runtime breakage

概念辨析
--------

* API compatibility 不等于 ABI compatibility；源码能重新编译成功，不代表旧二进制能直接加载。
* Limited API 不等于 Stable ABI 本身；它是达到 Stable ABI 目标的编译期约束手段。
* ``abi3`` 不代表“任何 Python 3 都能运行”，它仍有最低 CPython 版本和平台限制。
* wheel tag 是发布元数据，不是自动 ABI 验证器。
* public API 也可能只保证源码兼容，不一定属于 Stable ABI。
* 使用宏不一定错误；问题在于宏是否属于目标稳定性层级、是否暴露内部布局依赖。
* Stable ABI 减少构建矩阵，不减少语义测试矩阵。

本章结论
--------

扩展兼容性要沿“源码 API -> 二进制 ABI -> wheel tag -> 目标运行时”四层检查。若目标是跨 CPython 小版本复用，应先确定最低版本，再使用 Limited API 收窄源码依赖，确认二进制只依赖 Stable ABI，并以 ``abi3`` 发布和跨版本测试；任何 internal API 或布局依赖都会重新扩大兼容性风险。
