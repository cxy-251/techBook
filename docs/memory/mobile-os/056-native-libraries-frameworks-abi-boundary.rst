第056章：Native Libraries, Frameworks, ABI Boundary
==================================================

核心知识点
----------

* Native library 是已经编译为机器码、被加载进进程地址空间的代码模块，常用于媒体、图形、加密、AI、游戏和跨平台核心逻辑。
* Native code 运行在当前进程已有的 sandbox 和权限下；使用 C/C++/Rust 不会绕过系统权限模型。
* ABI 规定二进制之间如何传参、返回、布局结构体、使用寄存器和栈、导出符号以及保持 binary compatibility。
* Calling convention、数据对齐、对象布局、C++ name mangling、异常模型和标准库版本都可能成为 ABI 兼容点。
* Android 常通过 ``.so + JNI + NDK`` 连接 managed runtime 与 native 代码；Apple 常通过 framework / dylib、C ABI、Objective-C / Swift bridge 连接 native 能力。
* Public ABI 是平台承诺的稳定依赖面；private system ABI、vendor library 和未公开 framework 不应被普通 App 当成长期兼容接口。
* Native code 的主要风险是越界、悬空指针、double free、线程竞态、ABI 不匹配和私有依赖导致的版本崩溃。

关键路径
--------

应用调用 native 模块的通用路径：

``App Runtime → JNI / Swift-ObjC-C Bridge → App Native Library → Public ABI / Framework → System Service → Kernel / Driver``

加载与调用路径：

``二进制文件 → Dynamic Linker → 架构 / ABI 检查 → 符号解析 → 可调用入口 → 参数与对象跨边界 → 返回值 / 回调``

排查顺序：

#. 先判断库属于 App 自带、系统公开、系统私有还是 vendor library。
#. 加载失败先查目标架构、依赖库、搜索路径和未解析符号。
#. 进入 bridge 后再查 JNI 签名、结构体布局、对象 ownership 和线程归属。
#. Native crash 再依据 signal、backtrace、allocator 错误和地址访问定位内存问题。
#. 平台升级后才出现的问题优先检查 private ABI / private framework 依赖。

概念辨析
--------

* **API 与 ABI**：API 是源码级调用约定；ABI 是编译后二进制真正遵守的机器级约定。
* **JNI 与 NDK**：JNI 是 managed/native 调用桥；NDK 是 Android 提供的 native 开发工具与公开 API 集合。
* **Framework 与 Dynamic Library**：Framework 是带代码、资源和版本信息的封装；内部可包含动态库二进制。
* **Public ABI 与 Private ABI**：Public ABI 有兼容承诺；Private ABI 只服务系统内部实现，升级时可变化。
* **Native 性能优势 与 系统权限**：更直接的机器码执行不等于更高系统权限，两者属于不同边界。

本章结论
--------

Native boundary 的核心不是“代码更底层”，而是“二进制契约更严格”。稳定路径应建立在公开 ABI、明确 ownership 和受支持的 Framework / NDK 接口上；加载、符号、bridge 与内存问题必须分层定位，避免把所有 native crash 归成单一原因。