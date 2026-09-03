========================================================================
Chapter 38: 应用沙箱底层机制：Linux UID 隔离、SELinux 策略转换与 Apple Seatbelt 沙箱
========================================================================

.. note:: 前置背景与认知承接
   在前一模块中，我们深入剖析了移动操作系统的应用运行时与生命周期策略，追踪了 Android 平台 ART 虚拟机如何将 DEX 字节码演化为高效的 AOT/JIT 本地机器码，解构了基于 Zygote 写时复制（COW）的进程孵化微架构，以及 Apple 平台依托 Mach-O、dyld 4 动态链接器与 ARC 自动引用计数的原生运行机制。

   然而，无论应用程序的指令是以托管虚拟机形式解释执行，还是直接运行在 ARM64 裸机流水线上，一旦进程被操作系统加载并赋予执行权，它就面临着一个根本性的安全命题：**如何在物理单机多租户（Multi-Tenant）且宿主环境高度恶意的移动生态中，确保任意单个第三方应用既无法越权窃取、篡改同机其他应用与系统的私有数据，也无法绕过系统控制面直接操纵底层物理硬件？**

   传统桌面操作系统（如早期的 Linux、Windows 与 macOS）采用了开放式的用户信任模型：同一登录用户旗下的所有进程共享相同的凭证与访问权限，普通桌面软件拥有遍历用户家目录（``$HOME``）与访问任意非 root 系统对象的天然能力。移动平台从诞生伊始就彻底推翻了这一假设，确立了**互不信任的多租户对抗沙箱模型（Zero-Trust Mutual Adversarial Model）**。

   本章我们将深入移动操作系统安全体系的最底层基石，解构 Android 平台如何基于 Linux 内核传统的 UID/GID 自主访问控制（DAC）构建首层隔离，剖析 SELinux 强制访问控制（MAC）的 Domain 域转换、Type Enforcement 规则与 MCS 分类标签机制；同时深度横向映射 Apple 平台基于 AMFI 代码签名、Entitlements 凭证与 Seatbelt（``sandbox.kext``）内核扩展构建的容器化沙箱拓扑；最后解析 seccomp-bpf 系统调用过滤与 PAC 硬件指针认证在内核攻击面收敛中的纵深防御实现。

------------------------------------------------------------------------
38.1 移动沙箱的设计哲学与威胁模型
------------------------------------------------------------------------

移动操作系统在硬件上由单人全天候随身携带，集中了物理地理位置、双向音视频麦克风、生物特征识别（指纹/人脸）、银行支付令牌与全量个人通信隐私。然而，应用生态的开放性又允许用户自由下载安装数以百计由不同商业公司乃至个人开发者编写的第三方二进制包。这种“**高价值私密数据宿主环境**”与“**低信任度异构软件生态**”的剧烈碰撞，直接决定了移动沙箱的设计哲学。

桌面安全模型 vs 移动受控沙箱对比
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 桌面操作系统与移动操作系统安全威胁模型本质差异
   :widths: 18 41 41
   :header-rows: 1
   :class: tight-table

   * - 安全维度
     - 传统桌面操作系统 (Classic Desktop OS)
     - 现代移动操作系统 (Modern Mobile OS)
   * - **主体信任边界**
     - **以物理用户（User）为单一边界**。同一登录用户下的所有进程拥有同等权限，进程间默认可相互读取文件、枚举进程列表。
     - **以应用（Application Package）为最小隔离主体**。每个应用被视为独立不可信租户，应用间默认绝对隔离。
   * - **文件系统视图**
     - 全局开放文件系统。普通应用可自由读写 ``/home/user/`` 及其子目录，甚至扫描磁盘任意可读文件。
     - **容器化/隔离化文件视图**。应用仅能访问自身受严格沙箱限制的私有沙盒目录（Sandbox Container），跨应用文件直读被内核阻断。
   * - **IPC / 进程交互**
     - 支持无限制的本地 UNIX Socket、命名管道、信号发送、``ptrace`` 进程注入与内存抓取。
     - **全面中介化与凭据强制校验**。仅允许通过系统受控 IPC 通道（如 Binder、Mach Message/XPC）交互，传输自带硬核凭据，禁止直接内存调试。
   * - **硬件能力分配**
     - 应用可直接请求打开 ``/dev/video*``、``/dev/snd*`` 等字符设备节点，只要 DAC 文件权限允许即可占有硬件。
     - **硬件能力完全代理化**。禁止应用直持硬件设备文件句柄，所有硬件访问必须经由系统服务（CameraService、AudioFlinger 等）中介裁决。
   * - **访问控制范式**
     - 依赖自主访问控制（DAC: rwxrwxrwx）。资源所有者拥有自主赋权决定权，易受配置疏漏与提权木马攻击。
     - **自主访问控制 (DAC) + 强制访问控制 (MAC) 双重强制嵌套**。内核策略不可篡改，即使获得 root 权限仍受内核强制策略压制。

核心攻击面分类与纵深防御原则
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在移动操作系统内核视角下，未受约束的应用进程主要构成四大核心安全威胁：

1. **横向数据越权（Lateral Data Theft）**：恶意应用 A 试图直接读取、篡改合法金融应用 B 的私有数据库（SQLite）、SharedPreferences、Cookies 或本地加密密钥；
2. **纵向特权提升（Vertical Privilege Escalation）**：应用利用内核未修补的漏洞（如 UAF 释放后引用、整数溢出、条件竞争）突破 EL0 用户态，篡改内核态数据结构（如进程凭据），获取 root/内核特权；
3. **硬件资源嗅探与静默监听（Hardware Resource Snooping）**：应用绕过系统服务权限弹窗，私自打开底层传感器硬件节点，在后台静默录音、拍摄或扫描局域网设备；
4. **系统核心组件伪造与混淆代理（Confused Deputy Attack）**：恶意应用构造伪造 IPC 报文，诱骗具备高权限的系统服务（如 ``system_server``）代替自己执行高危操作。

为了消除上述威胁，移动系统确立了**纵深防御体系（Defense-in-Depth）**：任何一次敏感资源访问，必须连续、无断裂地通过“代码签名认证 $	o$ 运行时 UID/容器隔离 $	o$ 内核 MAC 强制访问控制 $	o$ 系统服务权限校验 $	o$ 系统调用白名单过滤”五道递进防线。

------------------------------------------------------------------------
38.2 Linux UID/GID 权限机制在 Android 沙箱中的特化
------------------------------------------------------------------------

在传统 Linux 服务器与桌面系统中，User ID（UID）的设计初衷是区分“物理上坐在终端机前的不同人类用户”，如系统管理员（UID 0）、数据库运维人员（UID 1001）或访客（UID 1002）。Android 架构师在 Linux 宏内核基础之上实施了一次精妙的语义置换：**将 Linux 的多用户（Multi-User）机制降维并特化为应用级隔离沙箱（Application Sandbox）**。

应用专属 UID 的分配与多用户数学公式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Android 系统中，每一个安装到设备上的 APK 应用都会在安装时由 ``PackageManagerService``（PMS）分配一个全系统唯一的 Linux UID。从此，该应用生成的所有进程、创建的所有私有文件与发起的 IPC 通信，均被打上该 UID 的物理烙印：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  Android UID 空间划分与多用户数学映射结构                |
   +-------------------------------------------------------------------------+
   UID = (User_ID * 100000) + (App_ID % 100000)

   0           9999 10000       19999                                200000
   +---------------+---------------+-----------------------------------+
   |  系统保留 UID  | 主用户应用 UID | 次级用户 (User 1) / 工作资料空间  |
   | (System/Root) | (User 0 Apps) | (Work Profile: 100000 + AppID)    |
   +---------------+---------------+-----------------------------------+

.. list-table:: Android 系统 UID 分段与物理映射规则
   :widths: 20 20 60
   :header-rows: 1
   :class: tight-table

   * - 标识范围 (Constant)
     - 数值区间
     - 系统语义与使用场景
   * - **AID_ROOT**
     - ``0``
     - Linux 超级管理员，仅供 ``init`` 及极少数底层引导守护进程使用。
   * - **AID_SYSTEM**
     - ``1000``
     - 核心系统服务共享 UID，``system_server``、SurfaceFlinger 等常驻骨干服务运行于此。
   * - **AID_APP_START**
     - ``10000``
     - 普通第三方应用 App ID 的分配起始基准线（``FIRST_APPLICATION_UID``）。
   * - **AID_APP_END**
     - ``19999``
     - 单个用户空间下第三方应用 App ID 的上限分配线（``LAST_APPLICATION_UID``）。
   * - **AID_USER_OFFSET**
     - ``100000``
     - **多用户步长偏移量（PER_USER_RANGE）**。用于在内核层面完全隔离多用户空间。

通过上述线性方程：
- 主用户（User 0）安装的应用（App ID 为 ``10086``），其进程 UID 严格等于：
  $$	ext{UID}_0 = 0 	imes 100000 + 10086 = 10086 \quad (	ext{对应名称形如 } 	exttt{u0\_a86})$$
- 当系统启用了“工作资料卡（Work Profile）”或多用户环境（User 10）时，同一应用安装在工作空间下的进程 UID 则被精确计算为：
  $$	ext{UID}_{10} = 10 	imes 100000 + 10086 = 1010086 \quad (	ext{对应名称形如 } 	exttt{u10\_a86})$$

这种数学结构使得底层 Linux 内核在完全不修改任何核心代码的前提下，天然支持了 Android 的多应用沙箱及多用户空间隔离。

私有目录 Inode 权限与 DAC 访问阻断
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当应用安装就绪后，系统安装守护进程（``installd``）会在物理闪存的内部存储分区下为该应用创建专属数据目录（``/data/user/<user_id>/<package_name>/``，通常软链接至 ``/data/data/<package_name>/``）。

此时，``installd`` 调用标准 Linux 系统调用 ``chown`` 与 ``chmod``，对该目录及其底层 Inode 施加极为严格的自主访问控制（DAC）标志位：

.. code-block:: text

   drwx------ 4 u0_a86 u0_a86 4096 2026-09-02 08:00 /data/data/com.example.map
   |  |  |
   |  |  +--> Other: --- (无读取、无写入、无执行/进入权限)
   |  +-----> Group: --- (无权限)
   +--------> Owner (u0_a86): rwx (读/写/执行完全归属主进程)

**DAC 判定阻断时序**：
1. 恶意应用进程（UID: ``10087``，即 ``u0_a87``）发起底层系统调用：``open("/data/data/com.example.map/databases/user.db", O_RDONLY)``；
2. Linux VFS 虚拟文件系统在解析路径分量时，检查目标 Inode 的 ``i_uid`` 字段（值为 ``10086``）与发起系统调用进程上下文中的 ``current_fsuid()``（值为 ``10087``）；
3. 检查判定发现进程 UID 既不匹配 Owner，也不在所属 Group 列表中，因此只能应用 Other 权限位（``---``）；
4. 内核立即无条件中断路径解析，向调用方进程返回 ``-EACCES``（Permission Denied）错误码。

这一机制无需触发任何 Java 虚拟机逻辑，完全在 Linux 内核的 VFS 路径查找快速分支（Path Lookup Fast-path）内被硬核阻断。

Android 辅助 GID 机制与受控权限下沉
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在早期 Android 架构中，系统还利用了 Linux 的多辅助组（Supplementary Groups / GID）机制，将平台的高层权限映射为内核级的网络或外部存储访问许可。例如：

- 声明了网络权限（``android.permission.INTERNET``）的应用，在 Zygote ``fork()`` 孵化出子进程时，会被赋予辅助组 ``AID_INET``（GID: ``3003``）；
- Linux 内核的网络套接字创建函数 ``sys_socket()`` 曾被植入补丁：当创建 ``AF_INET`` 族套接字时，必须检查当前进程是否属于 ``AID_INET`` 组，否则拒绝创建网络连接。

*(注：自 Android 10+ 引入 eBPF 网络过滤与 SELinux 深度治理后，过度依赖 GID 的粗粒度权限下沉模式已逐步收敛为基于内核网络过滤器与细粒度策略管治。)*

DAC 模型的物理缺陷与攻击逃逸
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

尽管基于 UID 的 DAC 沙箱极其轻量高效，但纯粹依赖 DAC 的系统存在无法逾越的物理缺陷：

1. **Root 提权后全线崩溃**：DAC 遵循“超级用户无上特权”原则。任何进程只要通过漏洞利用（如利用 setuid 二进制提权或内核未校验指针覆写）将自身凭据中的 ``uid`` 改写为 ``0``，整个 DAC 访问控制体系瞬间归零，所有应用的私有数据向其完全敞开；
2. **Confused Deputy（混淆代理）漏洞**：具有合法高权限的守护进程（如 ``mediaserver``、``installd`` 或 ``system_server``）必须持有跨多目录操作的特权。若高权限进程在处理低权限 App 传入的非受信文件描述符或路径时未进行充分的边界校验，恶意 App 即可诱骗系统服务代替自己去读写其他私有文件；
3. **客体自主赋权滥用**：DAC 允许资源所有者任意修改自身文件的权限位（如调用 ``chmod(..., 0777)``）。一旦某个设计不良的应用被本地注入或诱骗开放自身目录，其他应用便可乘虚而入。

为了解决 DAC 在超级权限面前的脆弱性，Android 引入了基于 NSA 规范的强制访问控制系统——**SELinux**。

------------------------------------------------------------------------
38.3 SELinux 强制访问控制：Domain 转换与 Type Enforcement
------------------------------------------------------------------------

Security-Enhanced Linux（SELinux）是构建在 Linux 安全模块（LSM - Linux Security Modules）钩子架构之上的**强制访问控制（MAC - Mandatory Access Control）**系统。在 MAC 模型中，不再存在所谓的“超级用户无上特权”，无论进程的 Linux UID 是 ``10086`` 还是超级管理员 ``0``（root），系统中的每一个动作（读取、写入、绑定套接字、发送 Binder 事务等）都必须在内核安全策略数据库中存在明确正向授权的 **Allow 规则**，否则一律被内核强制驳回。

SELinux 核心概念四元组
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 SELinux 体系中，操作系统中的每一个主体（进程）和客体（文件、目录、套接字、字符设备、Binder 接口等）都被赋予一个称为 **Security Context（安全上下文）** 的标签字符串，其标准格式遵循四元组结构：

.. code-block:: text

   user : role : type/domain : mls_level

   例如一个典型普通应用的上下文:
   u:r:untrusted_app:s0:c512,c768

   例如系统服务的上下文:
   u:r:system_server:s0

   例如应用私有数据目录文件的上下文:
   u:object_r:app_data_file:s0:c512,c768

- **User (用户)**：在 Android 中统一固定为 ``u``，不区分实际 Linux 用户；
- **Role (角色)**：对于主体（进程）固定为 ``r``，对于客体（文件/设备）固定为 ``object_r``；
- **Type / Domain (类型/域)**：**SELinux 策略的绝对核心**。当修饰主体（进程）时称为 **Domain（域）**，如 ``untrusted_app``、``system_server``、``shell``；当修饰客体（文件/资源）时称为 **Type（类型）**，如 ``app_data_file``、``camera_device``、``system_file``；
- **MLS / MCS Level (多级安全/多分类安全)**：形如 ``s0:c512,c768``。Android 巧妙运用其中的 **MCS 分类标签（Categories）** 实现了同 Domain 内部的进程级物理隔离。

Zygote 孵化与 Domain 动态转换时序
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当用户点击图标启动应用时，应用进程由 ``zygote`` 主进程孵化而来。但 ``zygote`` 自身运行在高度特权的 ``u:r:zygote:s0`` 域中（拥有映射应用内存、挂载沙箱、动态配置环境变量等系统特权）。新生成的应用进程必须在执行任何第三方代码前，**不可逆地将自身 Domain 降级进入低权限的受限沙箱域**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             Android Zygote 孵化进程与 SELinux Domain 转换时序            |
   +-------------------------------------------------------------------------+
   SystemServer (AMS)                 Zygote (u:r:zygote:s0)           Child Process
          |                                     |                            |
          |-- 1. writeSocket(args, package) --->|                            |
          |                                     |-- 2. fork() -------------> |
          |                                     |    (复制父进程页表与上下文)  |
          |                                     |                            | [处于 zygote 域]
          |                                     |                            |-- 3. selinux_android_setcontext()
          |                                     |                            |    - 解析 UID 与 targetSdkVersion
          |                                     |                            |    - 查询 seapp_contexts 规则映射
          |                                     |                            |    - 计算 MCS 类别: c512,c768
          |                                     |                            |    - 调用 /proc/self/attr/current
          |                                     |                            |      向内核请求上下文变更
          |                                     |                            |      (不可逆地蜕变为 untrusted_app)
          |                                     |                            |
          |                                     |                            | [进入 untrusted_app 域]
          |                                     |                            |-- 4. drop_capabilities()
          |                                     |                            |    (彻底抹去所有 Linux Capabilities)
          |                                     |                            |-- 5. setuid(u0_a86), setgid(u0_a86)
          |                                     |                            |-- 6. seccomp_filter_install()
          |                                     |                            |-- 7. 载入主 Activity 类并执行

**关键安全断言**：
步骤 3 中的 ``selinux_android_setcontext()`` 是单向不可逆的。一旦进入 ``untrusted_app`` 域，SELinux 策略中绝对不存在允许其转换回 ``zygote`` 或任何更高特权域的规则。即使后续注入的恶意代码设法获得了当前进程的全部执行权，它也永远被钉死在 ``untrusted_app`` 的策略牢笼之中。

Type Enforcement (TE) 规则与 Neverallow 平台硬红线
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

SELinux 的核心裁决依据是 **Type Enforcement（类型强制）** 规则。所有允许的系统行为必须通过 ``allow`` 声明显式给出：

.. code-block:: text

   # 标准 Allow 规则语法
   allow <source_domain> <target_type> : <class> { <permissions> };

   # 范例 1: 允许第三方应用读取并写入自身标识的数据文件
   allow untrusted_app app_data_file : file { read write open getattr create unlink };

   # 范例 2: 允许第三方应用向 ServiceManager 发起 Binder 通信以寻找公共系统服务
   allow untrusted_app servicemanager : binder { call transfer };

如果某个操作没有在策略文件中被明确 ``allow``，内核 LSM 钩子直接返回拒绝（默认拒绝原则）。

**Neverallow：不可打破的架构红线**：
AOSP 源代码中包含了成千上万条以 ``neverallow`` 开头的硬性编译时断言。这些规则在编译生成最终系统镜像时由策略编译器（``checkpolicy``）强制执行。若某家 OEM 厂商为走捷径，在自己的私有策略中允许了第三方应用直接访问底层物理块设备，系统构建将直接抛出致命错误中断：

.. code-block:: text

   # AOSP 核心安全硬约束规则示例:
   # 严禁任何非系统特权应用直接读写裸块设备 (Block Device)
   neverallow untrusted_app block_device : blk_file { read write open ioctl };

   # 严禁普通第三方应用向系统属性服务注入敏感系统配置
   neverallow untrusted_app default_prop : property_service set;

   # 严禁普通应用直接加载未经验证的内核模块
   neverallow untrusted_app self : capability sys_module;

MCS 分类标签隔离：多租户同 Domain 的数学解法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

全系统可能同时运行数十个第三方应用，它们在 SELinux 视角下**共享完全相同的 Domain——``untrusted_app``**。与此同时，它们的数据文件也具有相同的 Type——``app_data_file``。

如果仅依靠静态的 TE Allow 规则：
``allow untrusted_app app_data_file:file { read write };``
那么在 SELinux 层面，应用 A 岂不是可以随意读取应用 B 的数据文件？（此时只能退回依赖 DAC 检查）。

为了彻底根除对 DAC 的单一依赖，Android 启用了 **MCS（Multi-Category Security）机制**：
1. 系统维护一个拥有 1024 个独立敏感分类（Categories）的数学全集：$\{c_0, c_1, \dots, c_{1023}\}$；
2. 当应用安装分配 UID 时，系统通过散列算法为该应用随机生成一对**绝对不重叠的双分类标签（Category Pair）**，例如：
   - 应用 A（UID 10086）绑定：``c512,c768``
   - 应用 B（UID 10087）绑定：``c123,c456``
3. 应用 A 进程被启动时，其安全上下文被赋予：``u:r:untrusted_app:s0:c512,c768``；
4. 应用 A 在其私有目录下创建文件时，内核 SELinux 子系统自动将其私有文件的标签同步打为：``u:object_r:app_data_file:s0:c512,c768``；
5. **MCS 支配性（Dominance）判定法则**：当主体尝试访问客体时，**主体的分类集必须完全包含（Dominate）客体的分类集**。

.. code-block:: text

   应用 A (进程) : [c512, c768]
   应用 A (文件) : [c512, c768]  --> 完全匹配: SELinux MAC 允许访问通过

   应用 B (进程) : [c123, c456]
   应用 A (文件) : [c512, c768]  --> 无交集: SELinux MAC 强行阻断! 记录内核审计日志:
                                     type=1400 audit: avc: denied { read } for
                                     scontext=u:r:untrusted_app:s0:c123,c456
                                     tcontext=u:object_r:app_data_file:s0:c512,c768
                                     tclass=file permissive=0

即使恶意攻击者攻破了某个原生 C/C++ 库，通过汇编将当前进程的 Linux DAC UID 强行伪造修改，由于进程安全上下文由内核 task 结构体只读维护且受 MCS 约束，它依然绝对无法越权读取其他应用的数据文件！

------------------------------------------------------------------------
38.4 Apple 平台沙箱架构：AMFI、代码签名、Entitlements 与 Seatbelt
------------------------------------------------------------------------

在移动计算的另一核心阵营——Apple 平台（iOS / iPadOS / watchOS / visionOS），系统并非基于 Linux 宏内核，而是立足于 **Darwin / XNU 混合微内核架构**。Apple 围绕其私有内核扩展与密码学体系，演进出一套软硬件一体化的受控应用沙箱机制。

AMFI 与强制代码签名（Mandatory Code Signing）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 iOS 上，沙箱体系的第一道生死关隘并非运行时的文件隔离，而是静态的 **AMFI（Apple Mobile File Integrity）内核扩展** 与强制代码签名。

与 Android 允许用户自行侧载未知来源 APK 不同，iOS 在操作系统内核层面上推行了绝对的 **代码签名强制原则（Enforced Code Signing）**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     Apple AMFI 代码签名与页级完整性校验                  |
   +-------------------------------------------------------------------------+
   Mach-O 物理文件:
     +---------------------------------------------------------------------+
     | __TEXT Segment (只读代码段: 按 16KB 页物理切分)                       |
     |   Page 0 (4KB/16KB) -> SHA-256 Hash 0                              |
     |   Page 1 (4KB/16KB) -> SHA-256 Hash 1                              |
     |   Page 2 (4KB/16KB) -> SHA-256 Hash 2                              |
     +---------------------------------------------------------------------+
     | LC_CODE_SIGNATURE (Code Directory Blob):                            |
     |   - 物理页哈希树数组 [Hash 0, Hash 1, Hash 2 ...]                     |
     |   - 开发者证书链 (Developer / App Store CA)                          |
     |   - 嵌入式授权声明 (Embedded Entitlements Blob)                     |
     |   - Apple 权威签名 (RSA/ECDSA 签名根)                               |
     +---------------------------------------------------------------------+
                                   |
                                   v (内核缺页中断 Page Fault 触发)
   XNU 内核 (vm_fault_enter) ---> 调用 AMFI MAC 钩子
                                   |
                                   +--> 计算即将读入物理页的实时 SHA-256
                                   +--> 匹配 Code Directory 预留哈希
                                   +--> 一致: 建立页表映射, 允许 CPU 取指执行
                                   +--> 不一致/未签名: 发送 SIGKILL, 进程瞬间蒸发!

**物理安全推导**：
XNU 内核绝对禁止执行任何在内存中动态生成的未知机器码（除非具备特殊的调试特权）。内存页严格遵循 $W \oplus X$（Write XOR Execute，不可同时可写且可执行）硬件内存保护。这从源头上消除了攻击者向应用内存注入 Shellcode 并直接跳转执行的传统攻击路径。

Entitlements：写入签名资产的受控能力契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

如果说 Android 的权限申请是一份可动态调整的声明，那么 Apple 的 **Entitlements（授权权利）** 则是**在编译打包期以加密签名形式永久固化在 Mach-O 二进制内部的只读能力契约**。

Entitlements 底层是一个标准的 XML 属性列表（Property List），声明了应用请求的各项系统高危与共享特权：

.. code-block:: xml

   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
   <plist version="1.0">
   <dict>
       <!-- 允许跨进程共享钥匙串条目 -->
       <key>keychain-access-groups</key>
       <array>
           <string>TEAM123456.com.example.sharedkeychain</string>
       </array>
       <!-- 允许接入应用组共享存储容器 -->
       <key>com.apple.security.application-groups</key>
       <array>
           <string>group.com.example.weather</string>
       </array>
       <!-- 允许使用特定网络扩展 -->
       <key>com.apple.developer.networking.networkextension</key>
       <array>
           <string>packet-tunnel-provider</string>
       </array>
   </dict>
   </plist>

**签名锁死机制**：
开发者无法在本地随意伪造 Entitlements。Apple 开发者中心在签发配置文件（Provisioning Profile）时，会将该账号被允许启用的特权全集以苹果官方私钥签名。构建打包工具将 Entitlements 注入 Mach-O 的 ``LC_CODE_SIGNATURE`` 段中。当应用启动或尝试调用相关服务时，内核与系统守护进程（如 ``securityd``）直接提取经 AMFI 认证通过的签名 Entitlements 进行硬性比对。一旦检测到调用方未被授权某项 Entitlement，直接抛出 ``missing entitlement`` 异常并终止调用。

Seatbelt (sandbox.kext) 内核沙箱与容器化存储
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当应用通过 AMFI 校验启动后，XNU 内核中的专用安全模块——**Seatbelt（由内核扩展 ``sandbox.kext`` 实现）** 立即介入。

每一个第三方 App 在进入用户态执行之前，内核会为其编译并加载一份基于 Scheme 语言语法的沙箱配置文件（Sandbox Profile，如 ``container.sb``）：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       Apple iOS 应用容器物理目录拓扑                     |
   +-------------------------------------------------------------------------+
   /private/var/mobile/Containers/
     |
     +-- Data/Application/<Random-UUID-A>/       <-- 主应用专属私有数据容器
     |     +-- Documents/                        (用户显式数据, 参与云备份)
     |     +-- Library/
     |     |     +-- Caches/                     (缓存数据, 系统内存紧缺时可丢弃)
     |     |     +-- Preferences/                (NSUserDefaults 属性存储)
     |     +-- tmp/                              (临时工作目录)
     |
     +-- Shared/AppGroup/<App-Group-UUID>/       <-- 依据 Entitlements 共享的容器
           +-- Documents/                        (主 App 与 Today/Widget/Share
           +-- Library/Preferences/               Extensions 共享数据访问区)

**Seatbelt 运行态判定机制**：
1. **路径混淆与随机 UUID 隔离**：每一个安装的应用都被分配在以随机 128 位 UUID 命名的独立沙箱容器内。应用绝对无法通过相对路径跳出自身根目录；
2. **基于内核钩子的全系统调用拦截**：``sandbox.kext`` 在 XNU 内核的 VFS、Mach IPC、网络协议栈与 POSIX 接口处埋入拦截桩。当应用尝试调用 ``open()`` 访问自身 Container 之外的路径（如其他应用的容器目录或系统的 ``/private/var/preferences/``）时，Seatbelt 引擎直接阻断并返回 ``EPERM``（Operation not permitted）；
3. **Mach Service 白名单过滤**：iOS 应用与系统守护进程交互高度依赖 Mach Message / XPC 通信。Seatbelt 配置文件严格白名单化了当前应用有权查找并连接的 Mach 端口名称（如允许寻找 ``com.apple.uikit.viewservice``，但坚决禁止连接基带控制守护进程的 Mach Port）。

------------------------------------------------------------------------
38.5 Android vs Apple 移动沙箱全景架构对比
------------------------------------------------------------------------

为了深刻理解两套工业级移动安全体系的异曲同工与底层权衡，下表建立全景微架构对比：

.. list-table:: Android 沙箱与 Apple iOS 沙箱底层微架构全面技术映射
   :widths: 16 42 42
   :header-rows: 1
   :class: tight-table

   * - 技术对比维度
     - Android 平台 (AOSP)
     - Apple 平台 (iOS / Darwin)
   * - **主体身份基石**
     - **Linux 用户 ID（UID）**。每个应用被分配独立 UID，以原生 Linux 多用户作为主体边界。
     - **代码签名 Team ID + Bundle ID**。应用身份由苹果数字证书和嵌入的 Provisioning Profile 锚定。
   * - **强制访问控制引擎**
     - **SELinux（Security-Enhanced Linux）**。成熟的工业级 Type Enforcement 与 MCS 分类引擎。
     - **Seatbelt（``sandbox.kext``）**。基于 TinyScheme 规则解释器的私有轻量级内核访问控制沙箱。
   * - **应用执行受限域**
     - ``untrusted_app``（依据 API 级别细分为 ``untrusted_app_32``、``untrusted_app_34`` 等）。
     - ``container.sb``（定义了标准的 iOS 应用程序受限沙箱策略）。
   * - **多租户同质隔离手段**
     - **MCS 双分类标签组（Category Pairs）**。每个应用 UID 映射独立 ``cA,cB``，阻止同 Domain 互相读取。
     - **动态随机 UUID 物理路径注入**。内核沙箱配置仅动态绑定当前 App 专属的数据容器路径。
   * - **受控能力声明契约**
     - ``AndroidManifest.xml`` 中声明 ``<uses-permission>``，由平台与运行时动态授权解析。
     - **Entitlements（授权权利文件）**。编译期密码学签名内联锁定，由系统服务和内核强核验。
   * - **IPC 访问控制中枢**
     - **Binder 驱动**。内核在每次跨进程调用报文头中硬件直签 ``Calling UID/PID``，服务端权威校验。
     - **Mach Port / XPC 消息路由**。通过 ``launchd`` 与内核 Seatbelt 校验调用方 Mach 端口所有权及签名。
   * - **系统调用收敛技术**
     - **seccomp-bpf**。自 Android 8+ 启动，通过 Berkeley Packet Filter 白名单阻断未授权系统调用。
     - **沙箱系统调用限制**。由 ``sandbox.kext`` 在 XNU 内核分发层直接实施系统调用级拦截与屏蔽。

------------------------------------------------------------------------
38.6 纵深防御与内核攻击面收敛技术
------------------------------------------------------------------------

单纯依靠沙箱策略规则（SELinux 或 Seatbelt）只能约束“行为符合预期”的代码。然而，如果恶意应用蓄意向内核发送特制的畸形数据包，触发内核本身的 C/C++ 内存破坏漏洞，就能彻底推翻所有沙箱规则。因此，现代移动操作系统在应用沙箱内侧实施了极其激进的**内核攻击面收敛机制**。

seccomp-bpf 系统调用级白名单过滤
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Linux 内核暴露出多达 400 余个系统调用（System Calls）。对于一个普通用户态移动应用而言，它通常仅需与内存分配、线程同步、基本文件读写与网络套接字相关的几十个标准系统调用打交道。其余诸如 ``ptrace()``（进程注入调试）、``reboot()``（硬件重启）、``mount()``（文件系统挂载）、``swapon()``（交换分区控制）等高级或过时的系统调用，非但应用绝无理由调用，反而历史上多次爆发内核提权提权漏洞。

Android 自 8.0（Oreo）起在所有应用进程中强制推行 **seccomp-bpf（Secure Computing with Berkeley Packet Filter）**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     seccomp-bpf 内核系统调用过滤流水线                   |
   +-------------------------------------------------------------------------+
   应用线程 (EL0) 发起系统调用: mov x8, #NR_syscall; svc #0
                                        |
                                        v
   内核异常向量表进入 (EL1) ----> 触发 sys_call 表分发前
                                        |
                                        v (执行 seccomp BPF 字节码过滤程序)
                           [ 读取系统调用编号 x8 ]
                                        |
                 +----------------------+----------------------+
                 |                                             |
                 v (命中古老危险调用, 如 ptrace/mount)            v (命中合法常规调用, 如 read/write)
          [ 返回 SECCOMP_RET_KILL ]                     [ 返回 SECCOMP_RET_ALLOW ]
                 |                                             |
                 v                                             v
        内核直接向进程发送 SIGSYS 信号                   正式进入目标系统调用实现函数
        (非法进程被瞬时无情处决!)                       (sys_read / sys_write ...)

Zygote 在执行 ``fork()`` 之后、移交控制权给应用程序代码之前的最后一步，通过系统调用 ``prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ...)`` 装载一段预编译的 BPF 字节码程序。一旦装载，该线程及其派生的所有子线程均不可逆地受此过滤程序管辖，永远失去了向内核发起高危系统调用的物理能力。

内存硬化与现代硬件安全原语支撑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在硬件架构层面，移动芯片（ARM64）与操作系统紧密协同，构筑了三层不可逾越的硬件级内存硬化防线：

1. **ASLR 与内核 KASLR（地址空间布局随机化）**：
   - 进程虚拟内存中的代码段、堆、栈、动态库加载区在每次冷启动时被施加不可预测的随机偏移量（ASLR Slide）；
   - 攻击者无法依靠硬编码的内存绝对地址实施跳转，极大增加了 ROP（Return-Oriented Programming）利用链构建的成本；
2. **PXN (Privileged Execute-Never) 与 PAN (Privileged Access-Never)**：
   - **PXN**：ARM 体系结构通过页表项标志位保证：当 CPU 处于 EL1 内核态执行时，坚决禁止执行任何来自 EL0 用户态内存页中的指令代码（防御经典的 ret2usr 攻击）；
   - **PAN**：阻止内核驱动代码在未经过显式边界拷贝（如 ``copy_from_user``）的情况下，直接意外解引用读取或篡改用户态内存指针；
3. **PAC (Pointer Authentication Code，指针认证码)**：
   - 自 ARMv8.3-A 架构引入，被 Apple（A12+ 芯片，称之为 ``arm64e``）与高通现代旗舰芯片全面原生采纳；
   - 编译器在函数压栈保存返回地址指针（LR 寄存器）或虚函数指针时，利用 CPU 专用硬件指令 ``PACIASP``，以专用安全密钥与当前栈指针值作为盐值，计算一段加密校验码（PAC），并将其内联存入 64 位指针原本未使用的最高位比特段；
   - 在执行函数返回 ``RET`` 或虚表跳转前，CPU 强制执行 ``AUTIASP`` 校验 PAC 码。若攻击者通过栈溢出或堆溢出篡改了目标函数指针，PAC 校验瞬间崩溃，硬件直接触发未经捕获的 CPU 内存陷阱，使攻击利用直接转化为确定性的进程 Crash。

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章我们深入移动操作系统安全体系的根基，全面拆解了现代移动应用沙箱的底层构筑机制与跨平台微架构：
- 剖析了移动操作系统从传统桌面“物理用户信任”向“互不信任多租户受控沙箱”的设计哲学演进；
- 解构了 Android 平台将 Linux 多用户特化为应用沙箱的实现原理，推导了基于 UID/GID 的多用户隔离公式与 VFS Inode 级 DAC 访问阻断机制；
- 深入解密了 SELinux 强制访问控制（MAC）的深层运作拓扑，还原了 Zygote 孵化进程向 ``untrusted_app`` 域动态降级的不可逆时序，揭示了 MCS 双分类标签（Category Pairs）破解多租户同 Domain 访问冲突的数学解法；
- 横向映射了 Apple 平台立足于 AMFI 强制代码签名、Mach-O 嵌入式 Entitlements 凭证契约，以及基于 XNU 内核扩展 Seatbelt（``sandbox.kext``）与动态 UUID 容器构建的应用隔离体系；
- 确立了面向内核级提权利用的纵深防御模型，解析了 seccomp-bpf 系统调用白名单过滤与 ARM64 硬件指针认证码（PAC）收敛内核攻击面的微架构支撑。

在理解了应用如何在孤立受限的沙箱中安全运行之后，下一个不可回避的工程核心是：**应用与操作系统自身产生的绝密私钥（如银行卡支付令牌、全盘文件加密主密钥、用户生物认证凭据）究竟存放在哪里？** 如果宿主操作系统内核遭遇极高等级的物理入侵或零日漏洞提权，这些最高敏感级别的密钥如何免遭窃取？

在接下来的 **Chapter 39: 硬件密钥管理：Android KeyStore 与 Apple Secure Enclave (SEP)** 中，我们将跨越主处理器（Application Processor）的物理边界，深入探访芯片内部独立的硬件隔离安全岛——解构 Android 基于 ARM TrustZone TEE 与独立安全芯片 StrongBox 的 KeyMint 硬件抽象层，拆解 Apple 专有 Secure Enclave 协处理器（SEP）的独立内存加密引擎、硬件 AES 协处理器与基于物理硬件防回滚计数器的安全密钥生命周期管理。
