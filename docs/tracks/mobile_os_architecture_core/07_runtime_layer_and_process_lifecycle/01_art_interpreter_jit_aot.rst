========================================================================
Chapter 33: Android 运行时 (ART) 微架构：DEX 格式、解释器、JIT 与 AOT (dex2oat)
========================================================================

.. note:: 前置背景与认知承接
   在上一模块（Part 6: 系统服务与 IPC 通信中枢）中，我们系统剖析了 Android SystemServer 治理体系、Binder 驱动核心机制，以及 Apple launchd 与 XPC 守护进程网格。这些中枢服务构成了移动操作系统的控制面与通信骨干。

   然而，在移动操作系统应用层，绝大多数业务逻辑与框架代码并非直接以硬件裸机机器码形式分发，而是依托受管运行时（Managed Runtime）运行。在 Android 生态中，这一核心基座即为 **Android Runtime (ART)**。从 Dalvik 纯解释/JIT 虚拟机到 ART 全面 AOT，再到现代 Android 混合编译流水线（Interpreter + JIT + AOT + Profile-Guided Optimization），运行时架构的演进始终在启动延迟、运行性能、存储膨胀与电池能耗之间进行工程权衡。

   本章我们将深入 ART 的底层微架构，解构 DEX 文件的物理二进制布局与基于虚拟寄存器的指令集模型，追踪类加载与方法解析（Method Resolution）如何将离散符号转化为内存中的 `ArtMethod`，剖析 nterp 汇编解释器、JIT 即时编译、On-Stack Replacement (OSR) 以及 `dex2oat` AOT 编译流水线的状态机流转与底层实现。

------------------------------------------------------------------------
33.1 DEX 文件二进制拓扑与寄存器虚拟机模型
------------------------------------------------------------------------

从 Java 字节码到 DEX 紧凑二进制格式的演进
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

传统 Java 虚拟机（JVM）分发的标准载体是 `.class` 文件。每个 `.class` 文件包含单一类或接口的定义，拥有独立的常量池（Constant Pool）、字段与方法表。当数百个 Java 类被打包进 JAR 或 APK 时，海量重复的字符串（如包名、类型签名 `java/lang/String`）、冗余的类头元数据以及碎片化的 I/O 寻址，会带来严重的存储膨胀与内存映射开销。这在内存与闪存带宽严苛受限的移动终端上是不可接受的。

Android 引入了 **Dalvik Executable (DEX)** 格式。DEX 是面向移动设备专门设计的高度去重、跨类共享常量池的单一紧凑二进制文件：

.. list-table:: JVM Class 格式与 Android DEX 格式微架构特性对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 架构维度
     - JVM Class 字节码体系
     - Android DEX 二进制体系
   * - **文件组织粒度**
     - 单类单文件（1 Class per File），常量池各自私有且高度冗余。
     - 全包单文件或多文件（Multi-DEX），全包共享全局统一常量池。
   * - **虚拟机模型**
     - **基于操作数栈 (Stack-based)**：指令隐式压栈出栈，零地址或单地址指令为主。
     - **基于虚拟寄存器 (Register-based)**：指令显式操作 16 位虚拟寄存器，二地址或三地址指令为主。
   * - **指令密度与数量**
     - 字节码指令条数多，栈移动指令（`iload`, `istore`, `dup`）占比达 30%~45%。
     - 指令条数缩减约 30%，显式寄存器操作避免了无谓的内存栈压入弹出。
   * - **内存映射友好度**
     - 依赖 ZIP/JAR 解压加载，类加载时产生大量离散的小块内存分配。
     - 严格 4 字节边界对齐，直接通过 Linux `mmap()` 只读共享映射，多进程零拷贝复用。

DEX 文件的物理二进制布局
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

DEX 文件的内部拓扑被严格划分为三个核心物理区域：**文件头部 (Header)**、**索引区 (Identifiers)** 与 **数据区 (Data)**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       DEX 文件物理二进制内存布局                        |
   +-------------------------------------------------------------------------+
   | 0x0000: dex_header (112 Bytes)                                          |
   |         - Magic ("dex
039\0"), Checksum (Adler32), Signature (SHA-1)  |
   |         - file_size, header_size, endian_tag (0x12345678)               |
   |         - *_ids_size / *_ids_off 偏移量与项数表                        |
   +-------------------------------------------------------------------------+
   | string_ids (string_id_item[]: 4 Bytes per item -> offset to data)       |
   +-------------------------------------------------------------------------+
   | type_ids   (type_id_item[]:   4 Bytes per item -> string_id index)      |
   +-------------------------------------------------------------------------+
   | proto_ids  (proto_id_item[]:  12 Bytes per item -> shorty/return/params)|
   +-------------------------------------------------------------------------+
   | field_ids  (field_id_item[]:  8 Bytes per item -> class/type/name)      |
   +-------------------------------------------------------------------------+
   | method_ids (method_id_item[]: 8 Bytes per item -> class/proto/name)     |
   +-------------------------------------------------------------------------+
   | class_defs (class_def_item[]: 32 Bytes per item -> class_data_item off) |
   +-------------------------------------------------------------------------+
   | data section                                                            |
   |   - string_data_item (ULEB128 length + MUTF-8 bytes)                    |
   |   - type_list (参数类型列表)                                            |
   |   - class_data_item (static/instance fields, direct/virtual methods)    |
   |   - code_item (虚拟寄存器数量、入参、insns[] DEX 字节码流、try/catch)    |
   +-------------------------------------------------------------------------+

在 AOSP 源码（`art/runtime/dex/dex_file_structs.h`）中，DEX 头部严格对齐定义如下：

.. code-block:: c

   struct Header {
       uint8_t  magic_[8];           // "dex
039\0"
       uint32_t checksum_;           // Adler32 校验和，校验头部除 magic 与 checksum 外的数据
       uint8_t  signature_[20];      // SHA-1 签名，标识 DEX 文件内容哈希
       uint32_t file_size_;          // 整个 DEX 文件字节长度
       uint32_t header_size_;        // 头部大小，固定为 0x70 (112 字节)
       uint32_t endian_tag_;         // 字节序标记，标准为 0x12345678 (Little-Endian)
       uint32_t link_size_;
       uint32_t link_off_;
       uint32_t map_off_;            // map_list 的偏移量
       uint32_t string_ids_size_;    // 字符串 ID 项数 (上限 65536)
       uint32_t string_ids_off_;     // 字符串 ID 表文件内偏移
       uint32_t type_ids_size_;      // 类型 ID 项数
       uint32_t type_ids_off_;
       uint32_t proto_ids_size_;     // 方法原型 ID 项数
       uint32_t proto_ids_off_;
       uint32_t field_ids_size_;     // 字段 ID 项数
       uint32_t field_ids_off_;
       uint32_t method_ids_size_;    // 方法 ID 项数 (引发 64K Multi-Dex 瓶颈的核心上限)
       uint32_t method_ids_off_;
       uint32_t class_defs_size_;    // 类定义项数
       uint32_t class_defs_off_;
       uint32_t data_size_;          // 数据区总字节数
       uint32_t data_off_;           // 数据区起始偏移
   };

DEX 格式最具特色的去重机制体现于其**基于索引的间接引用链**：
1. `method_ids` 中的每一项占用 8 字节，包含 `class_idx`（指向 `type_ids`）、`proto_idx`（指向 `proto_ids`）与 `name_idx`（指向 `string_ids`）；
2. `proto_ids` 描述返回值类型与入参 `type_list`；
3. `type_ids` 仅包含一个 `descriptor_idx` 指向 `string_ids`；
4. 全局所有类、方法、签名中出现的 `"Ljava/lang/String;"` 字符串，在物理 DEX 中仅存储一份唯一的 MUTF-8 字符流，所有符号通过 16 位/32 位整型索引跨表关联。

虚拟寄存器架构与 code_item 解析
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

每个 Java/Kotlin 方法的真正执行体存储在数据区的 `code_item` 中。Dalvik/ART 将执行上下文抽象为一组**虚拟寄存器（Virtual Registers）**，用 `v0, v1, v2 ...` 标识：

.. code-block:: c

   struct CodeItem {
       uint16_t registers_size_;  // 该方法使用的虚拟寄存器总数 (含入参与局部变量)
       uint16_t ins_size_;        // 该方法接收的入参占用的寄存器数量
       uint16_t outs_size_;       // 该方法调用其他方法时所需的最大参数寄存器数量
       uint16_t tries_size_;      // try/catch 块的数量
       uint32_t debug_info_off_;  // 行号与局部变量调试信息偏移
       uint32_t insns_size_in_code_units_; // 指令区长度 (以 16-bit 为单位)
       uint16_t insns_[1];        // 紧随其后的 DEX 指令流数组
   };

在栈式虚拟机中，计算 `a = b + c` 需要执行 4 条指令：`iload b; iload c; iadd; istore a`。而在 ART 的寄存器虚拟机中，仅需一条紧凑的三地址指令：

.. code-block:: text

   add-int v0, v1, v2    // opcode: 0x90, 编码格式: 23x (v0 = v1 + v2)

寄存器分配约定：
- 若方法声明使用了 $N$ 个寄存器（`registers_size_ = N`），入参占用 $M$ 个寄存器（`ins_size_ = M`）；
- 入参被严格映射在最高的 $M$ 个寄存器中：`v(N-M) ~ v(N-1)`（在别名记法中常记为 `p0 ~ p(M-1)`）；
- 局域变量使用低编号寄存器：`v0 ~ v(N-M-1)`；
- 实例方法的 `p0`（即 `v(N-M)`）隐式保存调用者 `this` 引用。

------------------------------------------------------------------------
33.2 类加载与符号解析：PathClassLoader 到 ArtMethod 的运行时映射
------------------------------------------------------------------------

类加载双亲委派与 ClassLoader 继承拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Android 运行时类加载体系继承并重构了 Java 的双亲委派机制（Parent-Delegation Model）。与桌面 JVM 从离散的 `.class` 目录或 JAR 包中加载不同，Android 中的类加载器核心任务是从内存映射的 DEX 文件数组（`DexFile[]`）中线性检索符号。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Android 运行时 ClassLoader 继承与委托拓扑                 |
   +-------------------------------------------------------------------------+
   | BootClassLoader (C++ 实现，无 Parent)                                    |
   |   - 加载 /system/framework/ 核心系统库 (core-libart, framework.jar)      |
   +-------------------------------------------------------------------------+
                                      ^ (Parent)
                                      |
   +-------------------------------------------------------------------------+
   | PathClassLoader (继承自 BaseDexClassLoader)                             |
   |   - 加载应用 APK 安装目录 (/data/app/...) 主 DEX 与分包 DEX             |
   +-------------------------------------------------------------------------+
                                      ^ (Parent)
                                      |
   +-------------------------------------------------------------------------+
   | DexClassLoader / InMemoryDexClassLoader                                 |
   |   - 支持从只读外部存储路径或直接从内存字节流动态加载 DEX                 |
   +-------------------------------------------------------------------------+

`BaseDexClassLoader` 内部维持一个关键的 C++ 镜像对象——`DexPathList`，其数据结构包含一个 `Element[] dexElements` 数组：
1. 每个 `Element` 封装一个底层已打开的 `DexFile` 对象；
2. 当调用 `loadClass(name)` 时，加载器沿委托链递归向上询问 `BootClassLoader`；
3. 若父加载器无法解析，则遍历本地 `dexElements` 数组，依次调用底层 Native 接口 `DexFile_defineClassNative()` 在映射的 DEX 二进制中检索 `class_def_item`。

DexFile 的内存映射与 ClassLinker 类解析状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当应用启动装载 APK 时，ART 绝不一次性将数百兆的 DEX 文件完全读入堆内存，而是通过 Linux 内核系统调用 `mmap(..., PROT_READ, MAP_PRIVATE, fd, ...)` 将其建立为只读文件页映射。

类加载的核心引擎是位于 `art/runtime/class_linker.cc` 的 **`ClassLinker`**。一个 Java 类从 DEX 二进制符号转化为虚拟机可操作的内存实体，严格历经四大状态迁移：

.. list-table:: ClassLinker 类加载与初始化状态机
   :widths: 15 25 35 25
   :header-rows: 1
   :class: tight-table

   * - 状态阶段
     - 核心触发函数
     - 底层微架构操作
     - 产物与内存结构
   * - **1. Loading**
       (加载阶段)
     - `ClassLinker::FindClass`
     - 解析 DEX 中对应的 `class_def_item`，计算对象实例字段、静态字段与虚方法布局。
     - 在运行时堆（LinearAlloc）分配 `mirror::Class` 原型对象，标记为 `kStatusLoaded`。
   * - **2. Resolving**
       (解析阶段)
     - `ClassLinker::ResolveClass`
     - 解析父类（SuperClass）与实现接口（Interfaces），递归建立继承树。
     - 递归确保父类处于已加载状态，标记为 `kStatusResolved`。
   * - **3. Linking**
       (链接阶段)
     - `ClassLinker::LinkClass`
     - 构建虚方法分派表（vtable）与接口方法分派表（Interface Method Table - IMT）；校验字段与方法访问权限。
     - 实例化 `ArtMethod` 数组，重定位方法指针，标记为 `kStatusRetryVerificationAtRuntime` 或 `kStatusVerified`。
   * - **4. Initializing**
       (初始化阶段)
     - `ClassLinker::InitializeClass`
     - 加锁保护，调用当前类静态初始化块 `<clinit>()`，为 `static` 字段赋初值。
     - 状态置为 `kStatusInitialized`，类全面进入可安全调用状态。

ArtMethod 内存布局与调用跳板 (Trampoline)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ART 虚拟机内部，Java/Kotlin 的每个方法均被具体化为一个非托管的 C++ 对象——**`art::ArtMethod`**（位于 `LinearAlloc` 内存区，不参与 GC 垃圾回收）。

.. code-block:: c

   // ART 核心数据结构: art/runtime/art_method.h
   class ArtMethod {
       // 所属类对象指针 (GcRoot 弱引用)
       GcRoot<mirror::Class> declaring_class_;
       // 访问标志位 (public, private, static, synchronized, native 等)
       uint32_t access_flags_;
       // 在 DEX 文件中的 code_item 相对偏移量
       uint32_t dex_code_item_offset_;
       // 在 DEX method_ids 表中的全局索引
       uint32_t dex_method_index_;
       // 在所属类 vtable 或 imt 中的槽位索引
       uint16_t method_index_;

       // 关键执行入口指针
       struct PtrSizedFields {
           // 指向解释器调用该方法的跳板函数 (或 nterp 入口)
           void* entry_point_from_interpreter_;
           // 指向本地编译机器码 (JIT/AOT compiled code) 或 JIT 编译跳板
           void* entry_point_from_quick_compiled_code_;
       } ptr_sized_fields_;
   };

`ArtMethod` 的核心奥秘在于其**执行入口解耦设计**：
- 无论是解释器调用，还是已编译代码调用，调用端无需关心目标方法当前是以解释执行还是本地机器码执行；
- 当方法尚未被 AOT/JIT 编译时，`entry_point_from_quick_compiled_code_` 指向一个预设的汇编跳板函数（如 `art_quick_to_interpreter_bridge`）；
- 当 JIT 编译器在后台完成机器码编译后，原子化更新该指针直接指向本地机器指令入口。调用方无需任何代码补丁即可无缝切换至极速执行通路。

------------------------------------------------------------------------
33.3 解释器微架构：从 mterp 到 nterp 汇编快速解释器与 Shadow Frame
------------------------------------------------------------------------

解释器在移动设备上的战略地位
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在传统的服务端 JVM 中，解释器往往仅充当启动最初几毫秒的临时过渡，随后绝大多数代码均会被 C1/C2 编译器全面编译为机器码。但在智能手机场景下，这种激进的编译策略完全不可行：
1. **内存预算严苛**：一个典型的 Android 大型应用包含上万个方法，若全量编译为机器码，仅机器码尺寸（Code Size）即可达数十兆字节，直接耗尽系统的 ZRAM 与物理内存；
2. **长尾二八法则**：应用 80% 以上的代码（如配置解析、一次性初始化、冷门异常处理分支）全生命周期仅执行一次；
3. **即时响应需求**：应用冷启动时必须以零延迟瞬间进入主界面，不能容忍数十秒的安装期或启动期全量 JIT 阻塞。

因此，**高效的解释器是 ART 运行时的第一道防线**。

从 C++ Switch 解释器到 mterp 与 nterp 汇编演进
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ART 解释器历经三代微架构重构：

.. list-table:: ART 解释器三代微架构演进特征
   :widths: 15 25 35 25
   :header-rows: 1
   :class: tight-table

   * - 解释器代际
     - 典型版本
     - 核心调度机制
     - 性能瓶颈与物理特征
   * - **第一代: C++ 解释器**
     - Dalvik / 早期 ART
     - 基于标准 C++ `switch(opcode)` 或 GNU C 扩展标签跳转（Direct Threading）。
     - 每次分发伴随 CPU 分支预测失败惩罚；虚拟寄存器访问频繁读写内存，C++ 调用栈深度不可控。
   * - **第二代: mterp**
     - Android 7.0 ~ 11
     - 针对各 CPU 架构（ARM/ARM64/x86）手工编写纯汇编代码，单指令分派表对齐（Handler Table）。
     - 虽消除了 C++ 函数开销，但每个方法调用仍需在堆上显式分配 `ShadowFrame` 结构体，内存分配抖动大。
   * - **第三代: nterp**
     - Android 12+ (现代标准)
     - **新一代纯汇编解释器 (New Interpreter)**，深度模拟原生 C/C++ 调用栈约定（ABI）。
     - 彻底废除 `ShadowFrame` 堆分配，虚拟寄存器直接映射至物理 CPU 栈帧；性能接近轻量级 JIT。

nterp 物理执行模型与 ARM64 寄存器映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在现代 ARM64 架构上，nterp 将虚拟机的核心状态牢牢固定在物理 CPU 寄存器中，消除了任何跨层内存寻址开销：

.. list-table:: nterp 在 ARM64 硬件架构上的核心物理寄存器锁定分配
   :widths: 20 25 55
   :header-rows: 1
   :class: tight-table

   * - ARM64 物理寄存器
     - nterp 架构别名
     - 承载的虚拟机状态与职责
   * - `x19`
     - `rPC` (Program Counter)
     - 指向当前正在解码执行的 DEX 指令内存地址（`const uint16_t*`）。
   * - `x20`
     - `rFP` (Frame Pointer)
     - 指向当前方法栈帧中虚拟寄存器 `v0` 的物理基地址。
   * - `x21`
     - `rREFS`
     - 指向引用类型追踪表（用于精准型 GC 根集枚举）。
   * - `x22`
     - `rINST`
     - 缓存当前读取的 16 位 DEX 指令编码（包含 Opcode 与操作数寄存器索引）。
   * - `x23`
     - `rSELF`
     - 指向当前执行线程的物理指针（`art::Thread*`）。

在 nterp 架构下，执行方法调用的物理过程与执行标准 C 函数毫无二致：
1. **栈帧分配**：读取 `CodeItem::registers_size_`，一条 `sub sp, sp, #frame_size` 指令直接在物理线程栈上划出空间；
2. **入参拷贝**：调用方将实参存入 `sp` 顶部的虚拟寄存器槽位；
3. **指令循环**：
   - 提取 Opcode：`and w0, w22, #0xFF`；
   - 查分派表跳转：`ldr x1, [x_dispatch_table, w0, uxtw #3]; br x1`；
   - 执行操作：在汇编 handler 内完成加减运算并直接存入 `[rFP, #dest_reg_offset]`；
   - 步进 PC：`ldrsh w22, [rPC], #2` 并直接跳转到下一指令 handler。

------------------------------------------------------------------------
33.4 JIT 即时编译流水线：热度采样、CodeCache、OSR 与去优化
------------------------------------------------------------------------

JIT 编译器的触发模型与热度计数器 (Profiling)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当某个方法被频繁调用，或者方法内部存在运行耗时极长的循环体时，继续解释执行会浪费大量 CPU 时钟周期。ART 内置了一个自适应的 **JIT (Just-In-Time) 编译器**，在后台工作线程中异步将 DEX 编译为本地机器码。

热度追踪采用**两级计数器模型**：
- 每个 `ArtMethod` 内部包含一个动态计数器；
- 每次方法进入（Method Entry）或循环回边（Backward Branch）时，解释器将计数器累加；
- 系统根据属性配置决定触发门限：
  - `dalvik.vm.jitthreshold`：标准热度门限（默认通常为 10000 次调用/回边）；
  - `dalvik.vm.jitprithreadweight`：UI 主线程权重乘数。若当前执行线程为主线程，每次调用计为 3~5 次权重，加速 UI 关键路径热身。

当计数值突破门限时，ART 调用 `jit->AddCompileJob()` 向 JIT 线程池投递一个编译任务。**执行线程绝不挂起等待编译，而是继续以解释器模式流畅执行**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       ART JIT 异步编译与热度流转状态机                   |
   +-------------------------------------------------------------------------+
   | 方法调用 / 循环回边                                                      |
   |   |                                                                     |
   |   v                                                                     |
   | 解释器累加 ArtMethod 内部热度计数器                                      |
   |   |                                                                     |
   |   +---> 计数值 < Threshold: 保持 nterp 解释执行                         |
   |   |                                                                     |
   |   v 计数值 >= Threshold                                                  |
   | 向 JitThreadPool 投递异步编译请求 (Priority Queue)                      |
   |   |                                                                     |
   |   +-----------------------+                                             |
   |   | 执行线程: 继续解释执行 | (无卡顿用户交互)                             |
   |   +-----------------------+                                             |
   |   |                                                                     |
   |   v [JIT 后台线程]                                                       |
   | 1. 解析 DEX CodeItem -> 构建 HIR (High-level Intermediate Representation)|
   | 2. 类型特化、内联优化 (Inlining)、死代码消除                             |
   | 3. 生成 LIR (Low-level IR) -> 寄存器分配 (Graph Coloring / Linear Scan) |
   | 4. 汇编输出 ARM64 机器码 -> 写入 CodeCache                               |
   | 5. 原子更新 ArtMethod.entry_point_from_quick_compiled_code_              |
   |   |                                                                     |
   |   v                                                                     |
   | 下一次调用直接跳入 Native 机器码通道!                                   |
   +-------------------------------------------------------------------------+

JIT 内存空间管理：CodeCache 架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

JIT 编译生成的机器码存放在进程私有的 **CodeCache** 中。CodeCache 通过 `ashmem` 或匿名 `mmap` 分配，在物理上被严格划分为两个连续区域：
1. **Data Cache (读写权限 RW)**：存储编译元数据、GC 根集引用表（Roots table）以及 ProfilingInfo；
2. **Code Cache (执行权限 RX)**：存储可被 CPU 执行的 ARM64 机器指令。为满足移动安全 $W \oplus X$（Write XOR Execute）安全规范，ART 使用双映射内存（Dual-Mapping）或在代码写入时动态切换内存页权限。

CodeCache 设有硬性容量上限（通过 `dalvik.vm.jitmaxsize` 配置，典型值为 32MB~64MB）。当 CodeCache 空间耗尽时，ART 触发 **JIT Code Cache GC**：
- 遍历所有堆栈，扫描当前正在活跃执行的 JIT 帧；
- 驱逐冷门或低频 JIT 代码，将对应 `ArtMethod` 的入口指针重新重置回解释器跳板；
- 彻底回收废弃代码空间，防止应用运行时内存持续膨胀。

On-Stack Replacement (OSR) 栈上替换机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

若一个方法包含执行极其漫长的复杂 `for` 循环（如图像滤镜处理或大型 JSON 解析），该方法可能自启动后从未退出过。如果必须等待“下一次方法调用”才启用 JIT 机器码，整个循环将全程被迫承受解释执行的低效。

ART 引入了 **On-Stack Replacement (OSR)** 机制：
1. 解释器在执行循环回边指令（Backward Branch）时检测热度；
2. JIT 编译器专门为该循环体编译一段特殊的机器码，该机器码的入口不从方法头开始，而是直接对齐到循环体的起始指令；
3. **栈帧迁移**：运行时在物理栈上分配新的机器码栈帧，将当前解释器栈帧中的虚拟寄存器值逐一复制到机器码对应的物理寄存器/栈槽中；
4. 修改当前执行线程的指令指针（PC），让 CPU 直接在栈上无缝切换至本地代码执行循环，彻底终结了解释执行。

推测性优化与去优化 (Deoptimization)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了压榨出极致的性能，JIT 编译器会根据运行时收集到的 Profiling 数据进行激进的**推测性优化（Speculative Optimization）**：
- **单态内联 (Monomorphic Inlining)**：如果 Profiling 显示虚方法调用点 `obj.draw()` 在历史调用中 99% 的实例类型都是 `Circle`，JIT 直接将 `Circle.draw()` 的代码内联进来，并在前面加一道轻量级的类型断言（Class Check）；
- **常量传播与死分支消除**：根据观察到的运行时常量剪除未命中分支。

然而，动态语言特性决定了未来可能传入一个意外的 `Square` 实例，导致类型断言断裂。此时，CPU 无法继续执行该本地机器码。

ART 实现了高度精密的 **去优化（Deoptimization）** 机制：
1. 硬件类型断言失败，跳转到去优化跳板；
2. 捕获当前所有物理寄存器与栈状态；
3. 逆向重构出一个等价的解释器栈帧（`ShadowFrame`），将物理值映射回虚拟寄存器；
4. 恢复 `rPC` 指针指向触发断裂的原始 DEX 指令；
5. 无缝回退至解释器继续单步执行，同时清除该方法的推测编译结果，避免死锁。

------------------------------------------------------------------------
33.5 dex2oat 与 AOT 编译演进：OAT 文件格式、编译过滤器与 Profile 引导优化
------------------------------------------------------------------------

dex2oat 核心使命与架构演进
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

与 JIT 在运行时挤占 CPU 资源不同，**AOT (Ahead-Of-Time) 编译** 由独立的独立系统守护进程或命令行工具 **`dex2oat`** 在后台完成。

在 Android 5.0 引入 ART 之初，Google 曾激进地推行“安装期全量 AOT”（Full AOT）：
- 应用安装时，`dex2oat` 将 APK 内所有 DEX 方法全量编译为机器码，生成 `.oat` 文件；
- **痛点爆发**：大型应用安装耗时数分钟，系统 OTA 更新时出现令用户崩溃的“正在优化第 X 个应用，共 Y 个”，且生成的 `.oat` 机器码体积是原始 DEX 的 3~5 倍，极易撑爆用户存储空间。

因此，现代 Android（Android 7.0+ 至今）重构为**基于 Profile 的多阶段渐进式 AOT 架构**。

OAT 文件物理封装与 ELF 容器
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`.oat` 文件在物理本质上是一个标准的 **Linux ELF 共享库格式 (`.so`)** 二进制文件。通过复用 ELF 格式，ART 可以直接借助 Linux 内核动态链接器完成内存对齐、重定位以及基于代码段（`.text`）的多进程只读内存共享。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                         OAT 文件物理内部拓扑                            |
   +-------------------------------------------------------------------------+
   | 标准 ELF Header & Section Headers                                       |
   +-------------------------------------------------------------------------+
   | .rodata (Read-Only Data Section)                                        |
   |   - OatHeader (OAT 魔数 "oat
064\0", 校验和, 编译选项, DEX 文件计数)   |
   |   - OatDexFile 头部元数据 (原始 DEX 文件路径、校验和)                    |
   |   - [内嵌原始完整 DEX 数据] (DEX 字节码映射区)                           |
   |   - OatClass 头与方法状态位图 (编译状态: kOatClassCompiled/None)        |
   +-------------------------------------------------------------------------+
   | .text (Executable Code Section - RX)                                    |
   |   - 编译后生成的 ARM64 本地机器码指令流                                 |
   |   - Quick Method Code (Prologue, Method Body, Epilogue)                 |
   |   - 异常处理表 (OatExceptionTable) 与栈映射表 (StackMap)                |
   +-------------------------------------------------------------------------+
   | .bss (可读写全局变量区)                                                  |
   |   - 解析后的方法分派快速缓存、类型缓存                                   |
   +-------------------------------------------------------------------------+

当类加载器加载应用时，ART 优先检查是否存在匹配的 `.oat` 文件：
- 若匹配，直接 `mmap()` 加载 `.rodata` 与 `.text` 段；
- `ArtMethod` 的 `entry_point_from_quick_compiled_code_` 直接指向 `.text` 段中的固定物理机器码偏移，运行时直接飙至原生执行速度。

系统级编译过滤器 (Compiler Filters) 矩阵
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代 `dex2oat` 支持高度细化的编译过滤器（Compiler Filters），控制编译强度与产物体积：

.. list-table:: 现代 ART dex2oat 核心编译过滤器 (Compiler Filters)
   :widths: 18 15 35 32
   :header-rows: 1
   :class: tight-table

   * - 过滤器名称
     - 产物体积
     - 内部编译与校验行为
     - 典型系统应用场景
   * - **`verify`**
     - 极小 (无代码)
     - 仅执行 DEX 字节码格式合法性校验与类型安全检查，**不生成任何本地机器码**。
     - 应用商店刚下载安装完成时的初始状态；无 Profile 时的默认兜底。
   * - **`quicken`**
     - 极小
     - 展开部分调试信息，将部分虚方法调用优化为直接偏移查找，不生成机器码。
     - 兼容性测试与极低存储空间设备（Android 11 后逐渐废弃）。
   * - **`speed-profile`**
     - **中等 (黄金标准)**
     - **仅对传入的 Profile 文件中显式标记的热点方法与热点类执行 AOT 编译**，未标记代码保留解释执行。
     - **现代 Android 核心标准**：Google Play Cloud Profile 安装期编译、系统后台 dexopt 优化。
   * - **`speed`**
     - 极大 (膨胀 3x)
     - 对 DEX 中的所有方法进行全量深度 AOT 编译，包括全面循环展开与复杂方法内联。
     - `boot.oat` 系统核心框架库；跑分基准测试（Benchmark）。
   * - **`everything`**
     - 最大
     - 全量编译所有代码并尝试内联所有可能的方法，禁用任何解释兜底。
     - 工业开发与系统镜像极端调优（普通终端设备禁止开启）。

Baseline Profile 与 Cloud Profile 工业闭环
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了消灭新安装应用“首次冷启动卡顿”的系统缺陷，Android 引入了 **Baseline Profiles（基线配置文件）** 与 **Cloud Profiles** 闭环：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Android Profile-Guided 编译全生命周期闭环                |
   +-------------------------------------------------------------------------+

   [ 开发者阶段: Macrobenchmark 测试 ]
   开发者运行冷启动与核心交互用例 -> 生成 baseline-prof.txt
       |
       v (打包编译入 AAB/APK 根目录 assets/dexopt/baseline.prof)
   [ 应用发布: Google Play / 厂商应用商店 ]
       |
       +---> 结合全网成千上万真实用户的聚合运行日志
       +---> 云端聚合成全局最优的 Cloud Profile
       v
   [ 终端用户安装阶段 ]
   应用商店下载 APK 的同时，伴随下发编译好的二进制 Profile
       |
       v
   dex2oat 以 `speed-profile` 过滤器立即启动编译!
       |
       +--> 仅耗时 1~2 秒，精准完成 Application.onCreate()、
       |    首屏 Activity、布局解析关键方法的本地机器码编译!
       v
   [ 用户首次启动应用 ]
   关键路径 100% 命中 AOT 本地机器码，实现“开箱即极速”!

后台优化守护进程 (Background Dexopt)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于用户未被 Baseline Profile 覆盖的长尾个性化路径，系统依赖后台任务治理：
1. 当用户日常使用应用时，JIT 引擎将运行时的热点类与方法持续以二进制形式写入应用专属目录：`/data/misc/profiles/cur/0/<package_name>/primary.prof`；
2. 系统空闲管理中枢（`JobScheduler`）注册了一个每日夜间定时任务——**`BackgroundDexoptService`**；
3. 当且仅当设备同时满足**空闲状态（Idle）**且**连接外部充电器（Charging）**且**电池电量充足**时，后台编译作业被调度唤醒；
4. `dex2oat` 读取积累的运行时 Profile，将此前处于解释执行的热点路径增量增压编译入 `.oat` 文件中；
5. 用户第二天的启动与滑动体验获得完全透明的自适应性能跃升。

------------------------------------------------------------------------
33.6 混合执行模型与时空权衡：启动时延、内存驻留与存储占用的动态平衡
------------------------------------------------------------------------

运行时状态流转拓扑与优先级仲裁
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代 ART 运行时的最大架构精髓，在于它是一个**活性的多态执行体系**。一个 Java 方法在运行时绝非固步自封，其物理执行载体随时间与热度动态流转：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                    ART 单方法执行状态多态流转拓扑                       |
   +-------------------------------------------------------------------------+

                     [ 新安装未编译的冷方法 ]
                                |
                                v
                     (1) nterp 极速汇编解释执行
                                |
             +------------------+------------------+
             |                                     |
             | 调用频次 < 阈值                     | 调用频次 >= 阈值 (突破门限)
             v                                     v
       [ 保持解释执行 ]                   (2) JIT 异步编译进入线程池
       (零存储与内存开销)                          |
                                                   v
                                          [ 生成 JIT 机器码 ]
                                          (写入内存 CodeCache)
                                                   |
                             +---------------------+---------------------+
                             |                                           |
                             v 遭遇意外未推测类型                        v 正常调用
                     (3) 去优化 (Deopt)                                 [ 极速执行 JIT 机器码 ]
                     回退至 nterp 解释执行                                       |
                                                                                 | 写入运行时 Profile
                                                                                 v
                                                                 (4) 夜间空闲 Background Dexopt
                                                                                 |
                                                                                 v
                                                                        [ 固化为 AOT 本地机器码 ]
                                                                        (写入闪存持久化 .oat 文件)
                                                                                 |
                                                                                 v
                                                                      [ 下次启动直接从磁盘加载 ]

四大物理维度的工程取舍约束矩阵
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

移动平台受限于电池容量与芯片散热，任何单一维度的极致追求都会对其他系统指标造成毁灭性打击。ART 的混合架构是对四大物理约束严密权衡的工程折中：

.. list-table:: ART 混合编译执行在移动四大约束维度的权衡矩阵
   :widths: 18 20 20 20 22
   :header-rows: 1
   :class: tight-table

   * - 编译执行模式
     - 应用启动延迟 (Latency)
     - 峰值执行能效 (CPU/Jank)
     - 物理存储占用 (Storage)
     - 运行时内存驻留 (RAM/RSS)
   * - **纯解释执行**
       (Pure Interpreter)
     - **极快 (零编译等待)**
     - 极差 (频繁 CPU 周期与访存瓶颈)
     - **极优 (仅占 DEX 原始空间)**
     - **极优 (零额外 Code 占用)**
   * - **纯 JIT 模式**
       (Pure JIT)
     - 中等 (初次执行需热身)
     - 优 (针对真实硬件指令内联优化)
     - **极优 (闪存零膨胀)**
     - 差 (CodeCache 挤占宝贵物理内存)
   * - **全量 AOT**
       (Full AOT - speed)
     - 极快 (直接运行原生 ELF)
     - **极优 (无任何解释/编译开销)**
     - **极差 (ROM 膨胀 3~5 倍)**
     - 中等 (机器码随 Clean Page 按需换入)
   * - **现代混合流**
       (Profile-Guided)
     - **极快 (核心路径 AOT)**
     - **极优 (关键交互 100% 原生化)**
     - **优 (仅热点膨胀约 15%~25%)**
     - **优 (低频代码零 RAM 驻留)**

现代 Multi-DEX 布局优化原理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在大型应用构建阶段，`R8/D8` 编译器可以结合 `startup.prof` 执行 **DEX 布局重排（DEX Layout Optimization）**：
- 传统编译打包按包名字母顺序排列类定义，导致首屏必须调用的类离散分布在 DEX 的各个角落；
- 结合启动 Profile，编译器将应用冷启动首屏必须访问的全部类定义（`class_def_item`）与字节码指令（`code_item`）集中前置到 `classes.dex` 的起始连续地址段；
- **物理收益**：应用启动时，Linux 内核只需通过 Page Fault 触发数个连续的 4KB 页面读入即可覆盖全量启动逻辑，将闪存随机寻址彻底转化为顺序 DMA 读取，避免了数十次磁盘 I/O 阻塞造成的严重启动掉帧。

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章系统解构了 Android Runtime (ART) 的底层微架构与执行引擎体系：
- 剖析了 DEX 文件的物理二进制布局，对比了解析索引解耦机制与基于虚拟寄存器的指令集模型；
- 追踪了 ClassLoader 双亲委派模型及 `ClassLinker` 将 DEX 符号实例化为 `mirror::Class` 与 `ArtMethod` 的四阶段状态机；
- 深入解密了 nterp 纯汇编快速解释器利用 ARM64 物理寄存器锁定调度虚拟机的低延迟原理；
- 解构了 JIT 动态编译、热度门限、CodeCache 内存双映射、OSR 栈上替换以及去优化的物理闭环；
- 剖析了 `dex2oat` 基于 ELF 容器的 OAT 封装、细粒度编译过滤器矩阵，以及 Baseline/Cloud Profile 驱动的工业级渐进式优化闭环；
- 建立了在启动延迟、执行能效、物理存储与运行时内存之间的四维工程折中模型。

在应用托管运行过程中，随着业务逻辑的持续执行，海量临时对象在堆内存中被快速创建与丢弃。如何高效追踪对象可达性并在百兆级堆内存中执行回收，直接决定了移动端交互界面的帧率生死线。

在下一章 **Chapter 34: ART 并发垃圾回收 (CC-GC) 与停顿时间控制** 中，我们将深入 ART 的内存堆微架构，系统剖析 Concurrent Copying (CC) 垃圾收集算法、读屏障 (Read Barrier) 硬件加速、Baker 读屏障指针翻转以及毫秒级 UI 停顿控制的深层实现机制。
