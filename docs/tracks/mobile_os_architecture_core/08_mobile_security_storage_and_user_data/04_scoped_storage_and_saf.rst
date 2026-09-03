========================================================================
Chapter 41: 分区存储 (Scoped Storage) 与 SAF 框架访问控制
========================================================================

.. note:: 前置背景与认知承接
   在上一章中，我们解构了移动操作系统的持久化存储微架构与文件级加密（FBE）体系，剖析了 F2FS 日志结构文件系统的闪存友好机制，以及硬件内联加密引擎（ICE）如何确保数据在断电关机状态下以密文形式安全固化于 NAND 闪存颗粒中。至此，由底层文件系统与物理芯片构筑的存储机密性防线已经就绪。

   然而，将数据安全地写落磁盘只是存储治理的第一步。在多任务并发运行的移动操作系统中，更为严峻的挑战发生在应用运行期：**“当一个上层应用发起读写文件的请求时，操作系统根据什么规则判断其是否有权访问目标资源？其访问边界能延伸至多深？当涉及多应用共享与用户敏感数据时，系统如何杜绝越界窃取与存储污染？”**

   在移动操作系统的早期阶段，存储模型曾经历漫长的“混乱蛮荒期”。特别是早期 Android 体系为了兼容可插拔 SD 卡和 USB 大容量存储模式，向第三方应用开放了宽泛的全局外部存储读写权限（``READ/WRITE_EXTERNAL_STORAGE``）。任何声明该权限的应用均可随意遍历 ``/sdcard/`` 根目录下的任意文件，导致公有存储区沦为各应用私建目录、遗留孤儿垃圾、相互刺探隐私乃至植入持久化追踪标识（Covert Channels）的温床。与之相对，Apple 平台自 iOS 2.0 引入 App Store 起即确立了严密的 App Sandbox 容器隔离，但在面对跨应用文档协作与外部网盘整合时，同样面临如何将“用户显式授权”转化为受控文件访问句柄的架构挑战。

   为了彻底根除全局文件系统遍历带来的隐私灾难，现代移动操作系统重塑了存储访问模型：Android 引入了以 **分区存储（Scoped Storage）**、**FUSE 虚拟文件系统拦截层**、**MediaStore 多媒体元数据中枢** 与 **存储访问框架（Storage Access Framework - SAF）** 为核心的四层治理架构；而 Apple 平台则基于 **App Sandbox 容器**、**安全作用域 URL（Security-Scoped URL）**、**持久化书签（Security-Scoped Bookmark）** 与 **文件协调器（NSFileCoordinator）** 构筑了严密的就地编辑与授权流转网络。本章我们将深入移动操作系统的 VFS 内核层与系统服务框架层，系统剖析两大平台受限存储访问模型的微架构设计与工程权衡。

------------------------------------------------------------------------
41.1 移动外部存储的历史债务与访问模型危机
------------------------------------------------------------------------

要深刻理解分区存储的设计必然性，必须首先回溯智能手机存储抽象的发展历史。

早期 Android 外部存储的 FAT32 遗产与全局权限泛滥
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

早期的 Android 设备（如 HTC Dream / Nexus One）由于板载内部存储容量极其狭小（仅有几百兆字节用于存放系统与应用私有数据库），广泛依赖外置物理 MicroSD 卡作为主要用户存储空间。

这种硬件拓扑带来了深远的架构负资产：
1. **文件系统特权缺失**：外置 SD 卡格式化为微软 FAT32 文件系统。FAT32 属于面向个人电脑单用户设计的古老文件系统，**原生不支持 Linux 的 POSIX 文件属主（UID/GID）、权限位（Mode Bits）与 ACL 访问控制列表**；
2. **全局全暴露模型**：Android 内核只能在挂载该 FAT32 分区时，通过 VFS 挂载参数（``uid=media_rw, gid=media_rw, umask=0007``）施加粗暴的整盘统一权限。上层系统为了让应用能够保存照片和音乐，设计了粗粒度的 ``READ_EXTERNAL_STORAGE`` 与 ``WRITE_EXTERNAL_STORAGE`` 运行时权限；
3. **路径即权力（Path as Privilege）**：一旦用户授予某个应用外部存储权限，该应用便通过标准 C 语言 ``fopen()`` 或 Java ``File`` API 获得了对整个 ``/sdcard/``（即 ``/storage/emulated/0/``）目录树的无限制读写权力。

这种设计在移动互联时代迅速演化为系统级安全灾难：
- **公有存储公地悲剧（Storage Pollution）**：大量应用在 ``/sdcard/`` 根目录下滥建私有目录（如 ``/sdcard/tencent/``、``/sdcard/baidu/``、``/sdcard/alipay/``），应用在被卸载后，这些垃圾目录和残留文件永久驻留存储介质中，消耗宝贵的闪存空间并导致系统扫描严重卡顿；
- **隐蔽跨应用追踪信道（Covert Tracking Channels）**：在系统级设备硬件标识符（如 IMEI、MAC 地址、Android ID）被权限逐步收紧后，恶意广告 SDK 转向在外部存储的公共隐藏文件中写入自定义生成的唯一设备 UUID。当用户卸载重装甚至清空应用私有数据后，重新安装的新应用只需读取该公共文件，即可瞬间恢复用户的跨应用画像跟踪；
- **用户核心隐私全面失守**：一个仅需读取本地音频的音乐播放器或手电筒应用，在获取外部存储读取权限后，可以在后台静默扫描用户的全部家庭照片、微信保存的商业合同 PDF 以及下载目录中的个人账单，并将敏感数据悄然上传至分析服务器。

Apple App Sandbox 早期纯容器模型的演进压力
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

与 Android 的混乱演进截然相反，Apple 从 iOS 诞生之初就严厉执行 **App Sandbox（应用沙箱）** 隔离机制：
- 每个第三方应用完全封闭在独立生成的 UUID 数据容器内（``/var/mobile/Containers/Data/Application/<UUID>/``）；
- 应用对本地文件系统的读写仅限于自身的 ``Documents/``、``Library/`` 与 ``tmp/`` 目录；
- 系统中根本不存在面向普通应用开放的“公共共享文件系统根目录”。

然而，纯粹的沙箱容器模型虽然彻底根除了存储污染与交叉窃密，却在生产力场景下遭遇了**跨应用数据孤岛危机**：
- 用户在一个文字排版 App 中创建的文档，无法被另一个绘图 App 原地读取和追加图层；
- 早期唯一的共享途径是将文件通过系统的 Open In（UIDocumentInteractionController）机制**完整拷贝一份副本**到目标应用的沙箱中。这不仅导致大文件（如 4K 视频、大型设计工程）成倍消耗闪存空间，而且两份副本在不同应用中被各自修改后，瞬间产生无法调和的版本冲突；
- 随着 iPadOS 向专业桌面级生产力工具演进，以及云盘提供商（iCloud Drive、Dropbox、Google Drive）与外接 USB-C 移动硬盘的接入，Apple 必须打破静态沙箱的物理禁锢，在不破坏安全隔离的前提下，设计出一套“按需、就地（In-Place）、由用户意志主导的动态受控文件访问机制”。

两大平台在历史终局上殊途同归：**“彻底废黜基于绝对文件路径的静态全局读写特权，将存储访问权收缩为应用专属容器、类型化共享媒体中枢、以及基于用户交互意图的按需授权管道”**。

------------------------------------------------------------------------
41.2 Android 分区存储 (Scoped Storage) 微架构
------------------------------------------------------------------------

自 Android 10（API 29）初步引入、并在 Android 11（API 30）全面强制推行的 **分区存储（Scoped Storage）**，是 Android 存储架构历史上最激进、最底层的重构工程。

分区存储的核心设计哲学是：**“重新划分存储区域所有权，默认隔离私有数据，结构化接管共享媒体，由系统文件选择器代理文档交互，严格收回文件树遍历能力”**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     Android 分区存储四层空间划分模型                     |
   +-------------------------------------------------------------------------+
   [1. 内部私有存储 (Internal Storage)]
     - /data/user/0/<package>/files/ & cache/
     - 访问约束: 仅当前 App 的 Linux UID 可见, SELinux 强制隔离, 卸载自毁

   [2. 外部应用专属目录 (External App-Specific Storage)]
     - /storage/emulated/0/Android/data/<package>/files/ & cache/
     - 访问约束: 专属于当前 App, 读写无需任何存储权限, 卸载时系统联动删除;
     - 关键边界: Android 11+ 严禁任何其他普通第三方应用访问或遍历本目录!

   [3. 共享多媒体集合 (Shared Media Collections - MediaStore 接管)]
     - /storage/emulated/0/Pictures/, Movies/, Music/, Audio/, DCIM/
     - 访问约束: 必须通过 MediaStore API 访问, 自身创建的媒体免权限自由读写,
     - 访问他人媒体需申请精细化权限 (READ_MEDIA_IMAGES / VIDEO / AUDIO)

   [4. 共享文档与下载集合 (Shared Documents & Downloads)]
     - /storage/emulated/0/Download/, Documents/
     - 访问约束: 仅限创建者自由访问自身项; 访问其他应用的文件必须走 SAF 系统选择器

四层存储空间的生命周期与访问权限矩阵
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

分区存储将整个存储设备划分为边界清晰的四类空间，其访问机制与生命周期如表 41-1 所示：

.. list-table:: Android 现代存储分区特征与权限访问矩阵
   :widths: 15 25 20 20 20
   :header-rows: 1
   :class: tight-table

   * - 存储区域
     - 典型物理/逻辑路径
     - 访问所需权限
     - 卸载时是否清除
     - 对其他应用的可见性
   * - **内部应用私有**
     - ``/data/user/0/<pkg>/``
     - **无（免权限）**
     - **是**
     - **绝对不可见**（UID 与 SELinux 强隔离）
   * - **外部应用专属**
     - ``/sdcard/Android/data/<pkg>/``
     - **无（免权限）**
     - **是**
     - **不可见**（系统阻止其他 App 跨包访问）
   * - **共享多媒体**
     - ``Pictures/``, ``DCIM/``, ``Music/``
     - 读自身免权限；读他人需媒体权限
     - **否（永久保留）**
     - **可见**（通过 MediaStore 查询）
   * - **共享非媒体文档**
     - ``Download/``, ``Documents/``
     - 读自身免权限；读他人需走 SAF 选择器
     - **否（永久保留）**
     - **仅在用户通过 SAF 显式选择后可见**

内核 VFS 拦截演进：从 sdcardfs 到 FUSE 与 FUSE-BPF
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了在不修改 Linux 内核标准 POSIX 文件 API（如 C 库 ``open()``、``read()``、``stat()``）的前提下，动态拦截第三方应用对外部存储文件路径的直接访问并强制执行分区存储规则，Android 底层存储虚拟化架构经历了三代核心演进：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     Android 存储虚拟化底层技术演进                      |
   +-------------------------------------------------------------------------+
   [第一代: 早期用户态 FUSE (Android 4.3 以前)]
     App Syscall -> VFS -> 内核 FUSE 驱动 -> 上下文切换 -> 用户态 sdcard 守护进程 -> 内核 ext4
     (缺陷: 每次读写两次内核/用户态上下文切换与内存拷贝, I/O 吞吐极度低下)

   [第二代: 内核态 sdcardfs 堆叠文件系统 (Android 7.0 - 9.0)]
     App Syscall -> VFS -> 内核 sdcardfs 驱动 (硬编码 UID/GID 权限校验) -> 内核 ext4
     (优势: 全内核态执行, 性能极高; 缺陷: 规则固化于内核, 无法支持复杂的运行时权限动态判定)

   [第三代: 现代化 FUSE + FUSE-BPF 硬件卸载 (Android 11 - 15+)]
     App Syscall -> VFS -> 内核 FUSE 驱动 + eBPF Filter
                                 |
                                 +---> [快速路径: FUSE-BPF 命中已授权 fd] ---> 直接直通内核 F2FS/Ext4 (零开销)
                                 |
                                 +---> [慢速路径: 未授权 open()/unlink()] ---> 陷入用户态 MediaProvider (执行鉴权)

1. **早期用户态 FUSE 瓶颈**：
   - 所有文件系统调用必须在内核与用户态守护进程之间来回搬移数据，性能极其低下，大文件拷贝时 CPU 占用率居高不下；
2. **内核态 sdcardfs 的兴起与废弃**：
   - 为了解决 I/O 性能瓶颈，Google 引入源自三星的 ``sdcardfs`` 内核堆叠文件系统，在内核中完成 UID 权限检查；
   - 但 ``sdcardfs`` 的校验逻辑是静态固化的（仅根据路径与 GID 判定），无法在文件打开时动态向 Java 层 ``MediaProvider`` 查询数据库属主，更无法弹出授权弹窗，严重阻碍了分区存储的推进。自 Android 11 起，``sdcardfs`` 被官方从内核中彻底废黜；
3. **现代化 FUSE 与 FUSE-BPF 融合架构**：
   - 外部存储的挂载点由运行在用户态的 ``MediaProvider`` 进程以 FUSE（Filesystem in Userspace）文件系统挂载；
   - 当应用调用 ``open("/sdcard/Pictures/test.jpg")`` 时，内核 FUSE 驱动捕获该系统调用，将其打包为 FUSE 请求发送给用户态的 ``MediaProvider``；
   - ``MediaProvider`` 在用户态校验调用者的 UID、包名、当前前台状态以及该文件在 SQLite 媒体库中的属主关系。若鉴权通过，向内核返回真实底层物理路径（如 ``/data/media/0/Pictures/test.jpg``）的底层文件描述符；
   - **FUSE-BPF 极致加速**：为了避免后续高频的 ``read()`` 和 ``write()`` 产生反复跨越内核态与用户态的昂贵上下文切换（Context Switch），现代 Android 内核集成了 **FUSE-BPF** 模块：一旦首次 ``open()`` 鉴权完毕，后续所有数据流读写全部由内核 eBPF 虚拟机在内核态直通到底层 F2FS 文件系统，实现接近原生文件系统的无损读写吞吐。

全文件访问权限 (MANAGE_EXTERNAL_STORAGE) 的收敛边界
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于杀毒软件、全盘备份工具和专业文件管理器等确实需要遍历全局存储的极少数核心应用，Android 11 引入了特权级的 **``MANAGE_EXTERNAL_STORAGE``** 权限：
- 应用在 Manifest 中声明该权限后，无法通过标准运行时弹窗申请，必须显式引导用户跳转至系统专属设置页面（``Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION``）手动开启开关；
- 该权限获得批准后，应用将重新获得针对除专属私有目录外几乎所有公有路径的原始文件读写能力；
- **架构硬限制（Hard Sandbox Restrictions）**：即便获得了 ``MANAGE_EXTERNAL_STORAGE`` 特权，操作系统内核与 FUSE 驱动依然**坚决阻断**其访问其他应用的外部专属私有目录（``/sdcard/Android/data/`` 与 ``/sdcard/Android/obb/``），以此捍卫应用沙箱的终极边界；
- **应用商店政策锁死**：Google Play 与主流 Android 应用商店设立了极其严苛的自动化审计政策，任何非核心文件管理类应用（如社交、工具、电商 App）一旦声明此权限，直接判定违规下架。

------------------------------------------------------------------------
41.3 MediaStore 多媒体共享中枢与授权状态机
------------------------------------------------------------------------

在分区存储模型下，**``MediaStore`` 系统内容提供者（ContentProvider）** 正式成为所有共享媒体资源（图像、视频、音频及下载项）的唯一权威中心。

MediaStore 逻辑集合与底层 SQLite 架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``MediaStore`` 并非物理文件系统，其本质是一个维护在系统进程内部的 **SQLite 关系型数据库（``external.db``）**，配合文件系统监控器与扫描器（MediaScanner）实时追踪文件变动：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     MediaStore 系统多媒体数据中枢架构                   |
   +-------------------------------------------------------------------------+
   [上层应用程序] (使用 ContentResolver API)
         |
         |-- query() / insert() / openFileDescriptor()
         v
   [MediaProvider (com.android.providers.media.module 独立主模块 APEX)]
         |
         +---> [核心 SQLite 数据库: /data/databases/external.db]
         |       - 表: files (全量索引表: _id, _data, mime_type, is_pending, owner_package_name)
         |       - 视图: images, video, audio, downloads
         |
         +---> [FUSE 守护中枢: /system/bin/sdcard]
                 - 拦截 Native POSIX API 访问, 与 external.db 实时鉴权对齐

应用通过特定的内容 URI（Content URI）访问指定的多媒体逻辑集合：
- **``MediaStore.Images.Media.EXTERNAL_CONTENT_URI``**：对应照片图库；
- **``MediaStore.Video.Media.EXTERNAL_CONTENT_URI``**：对应视频库；
- **``MediaStore.Audio.Media.EXTERNAL_CONTENT_URI``**：对应音频录音与音乐；
- **``MediaStore.Downloads.EXTERNAL_CONTENT_URI``**：对应系统下载中心。

媒体写入生命周期与 IS_PENDING 原子保护机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在传统文件系统中，当应用向磁盘写入一个大型视频时，如果写入耗时数秒甚至数分钟，在此期间其他应用遍历相册，会读取到一个破损的未完成视频文件或空文件头，引发解码器崩溃。

``MediaStore`` 引入了 **``IS_PENDING`` 状态位机制**，实现了文件创建与对公发布的严格两阶段提交：

.. code-block:: java

   // 现代 Android 向 MediaStore 插入媒体文件的标准两阶段提交路径
   ContentResolver resolver = context.getContentResolver();
   ContentValues values = new ContentValues();
   values.put(MediaStore.Video.Media.DISPLAY_NAME, "HighSpeed_Render_4K.mp4");
   values.put(MediaStore.Video.Media.MIME_TYPE, "video/mp4");
   values.put(MediaStore.Video.Media.RELATIVE_PATH, Environment.DIRECTORY_MOVIES + "/StudioApp");
   // 阶段一: 标记为 PENDING 状态，对除当前应用外的全系统其他进程绝对隐形
   values.put(MediaStore.Video.Media.IS_PENDING, 1);

   Uri videoUri = resolver.insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, values);

   // 获取底层硬件文件描述符并持续流式写入数据
   try (ParcelFileDescriptor pfd = resolver.openFileDescriptor(videoUri, "w");
        FileOutputStream out = new FileOutputStream(pfd.getFileDescriptor())) {
       writeDataPayload(out);
   }

   // 阶段二: 写入全部落盘校验完毕后，原子将 IS_PENDING 翻转为 0，正式对公发布可见
   values.clear();
   values.put(MediaStore.Video.Media.IS_PENDING, 0);
   resolver.update(videoUri, values, null, null);

- 当 ``IS_PENDING == 1`` 时，底层 ``MediaProvider`` 在响应其他任何应用的查询请求时，会在 SQL 层面自动追加 ``WHERE is_pending = 0`` 过滤条件，第三方应用根本感知不到该文件的存在；
- 同时，写入应用可指定 ``RELATIVE_PATH``（如 ``Pictures/MyApp/``），系统负责将其自动映射到底层物理存储路径，应用无需也无法拼接绝对磁盘字符串。

修改他人创建媒体的提权机制与批量操作状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在分区存储下，应用**天然拥有其自身创建的所有媒体文件的全部读写与删除权力，无需任何权限**。但当应用需要编辑或删除由其他应用（如系统相机、其他社交软件）生成的照片时，系统施加了严格的交互授权边界：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             修改/删除他人媒体文件的 MediaStore 提权授权时序             |
   +-------------------------------------------------------------------------+
   应用 (App)           MediaProvider               系统界面 (System UI)       用户 (User)
       |                     |                               |                   |
       |-- update()/delete()-> (直接调用)                     |                   |
       |   (抛出 RecoverableSecurityException 异常)          |                   |
       |                     |                               |                   |
       |-- MediaStore.createWriteRequest(uris) ------------->|                   |
       |   (提交待编辑 URI 列表)                              |                   |
       |                     |-- 返回包含系统授权意图的 PendingIntent             |
       |<--------------------+                               |                   |
       |                                                     |                   |
       |-- startIntentSenderForResult(pendingIntent) ------->| (弹出系统级确认框) |
       |                                                     |-------- 提示用户 ->|
       |                                                     |<-- 确认/拒绝授权 --|
       |<-- onActivityResult() 接收授权成功结果 -------------|                   |
       |                                                     |                   |
       |-- 再次调用 resolver.openFileDescriptor(uri, "rw") ->|                   |
       |   (MediaProvider 校验内存已授权标记，成功开放写权限)  |                   |
       v                                                     v                   v

Android 11 进一步引入了系统级批量操作 API：
- **``MediaStore.createWriteRequest()``**：请求对一批外部媒体的修改权；
- **``MediaStore.createTrashRequest()``**：将媒体移入系统回收站（保留 30 天，而非永久硬删除）；
- **``MediaStore.createDeleteRequest()``**：请求永久删除一批外部媒体。

这一机制将“静默数据篡改风险”完全转化为“用户可视可控的显式知情同意”。

Android 13 精细化媒体权限与 Photo Picker 架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Android 13（API 33）中，Google 彻底终结了历史遗留的 ``READ_EXTERNAL_STORAGE`` 统一权限，将其切分为三个完全独立的细粒度权限：
- **``READ_MEDIA_IMAGES``**：仅授权访问相册图片；
- **``READ_MEDIA_VIDEO``**：仅授权访问视频文件；
- **``READ_MEDIA_AUDIO``**：仅授权访问音频文件。

一个录音剪辑软件若申请图片读取权限，将直接引发用户疑虑与平台警告。

更进一步，为了彻底消除应用“为了选一张头像就必须申请整个图片库权限”的过度授权问题，系统推出了 **Android Photo Picker（照片选择器）**：
- 照片选择器完全由系统进程（Google Play Services 或系统内置 MediaProvider）独立渲染展示；
- 宿主应用在整个选择过程中**对整个相册没有任何读取权限**，无法获知相册中有多少张照片及其元数据；
- 仅当用户在系统界面中亲自点击选中某 1~2 张照片并点击“确认”后，系统才通过临时 URI 授权（URI Grant）将这几张特定照片的读取能力精准授予该应用。这一架构将权限申请直接压降至 **0 权限（Zero-Permission Architecture）**。

------------------------------------------------------------------------
41.4 存储访问框架 (Storage Access Framework - SAF) 与 Document Provider
------------------------------------------------------------------------

对于多媒体以外的任意格式文件（如 PDF 电子书、ZIP 压缩包、CAD 工程图纸、源代码文本等），移动操作系统坚决禁止应用通过路径直接遍历共有磁盘。针对此类通用文档，Android 确立了 **存储访问框架（Storage Access Framework - SAF）**。

SAF 的三大核心契约与 DocumentsUI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

SAF 的核心交互完全围绕系统级文档选择界面——**DocumentsUI** 展开，应用通过三大标准 Intent Action 表达访问意图：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     SAF 三大核心 Intent 契约与操作语义                  |
   +-------------------------------------------------------------------------+
   [1. ACTION_OPEN_DOCUMENT]
     - 语义: 用户选择一个已存在的单个或多个文档 (导入场景, 如导入 PDF、导入证书)
     - 结果: 返回目标文件的 content:// URI 及单次读/写权限

   [2. ACTION_CREATE_DOCUMENT]
     - 语义: 用户指定一个新文件的存储位置与文件名 (导出/另存为场景, 如导出备份包)
     - 结果: 系统在目标 Provider 创建空占位项，返回该新文件的可写 content:// URI

   [3. ACTION_OPEN_DOCUMENT_TREE]
     - 语义: 用户显式授权一个完整的目录子树 (批处理与目录同步场景)
     - 结果: 返回代表该目录树根节点的 tree URI，应用可在该树形结构下自由遍历与创建子项

DocumentsUI 将本地闪存根目录、可移除 SD 卡、USB-OTG 闪存盘、Google Drive 云端盘乃至第三方自建网盘统一抽象为扁平的“存储提供源”。应用发起的仅是对能力的请求，决定权完全移交至用户指尖。

Document Provider 内部架构与底层虚拟化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

每一个向 SAF 贡献存储源的实体均需实现抽象类 **``DocumentsProvider``**。其内部并非简单的磁盘映射，而是一个标准的虚拟树形数据库：

.. code-block:: java

   // Document Provider 核心虚拟抽象接口契约
   public abstract class DocumentsProvider extends ContentProvider {
       // 查询提供者根节点 (如 "内部存储", "Google Drive 个人盘")
       public abstract Cursor queryRoots(String[] projection);
       // 查询指定文档/目录自身的元数据 (文件名, 大小, 权限标志位, MIME 类型)
       public abstract Cursor queryDocument(String documentId, String[] projection);
       // 展开指定目录节点，查询其所有直接子节点 (展开目录树)
       public abstract Cursor queryChildDocuments(String parentDocumentId, 
                                                 String[] projection, String sortOrder);
       // 根据客户端请求打开并返回底层文件描述符
       public abstract ParcelFileDescriptor openDocument(String documentId, 
                                                         String mode, CancellationSignal signal);
   }

- **Document ID 的非透明性**：``documentId`` 是 Provider 内部维度的字符串标识符，它可能对应本地绝对路径，也可能对应一个云端文件的对象 ID（如 ``drive_file_94827104``）。客户端严禁尝试对 ``documentId`` 进行路径截取或逆向解析；
- **ParcelFileDescriptor 穿透传递**：当应用通过 ``ContentResolver.openFileDescriptor(uri, "r")`` 打开文件时，Provider 可以返回一个基于物理文件的真实 FD，也可以通过内核管道（Pipe）构建一个跨进程异步写入的虚拟内存数据流，使得应用以一致的标准 POSIX 读取接口透明消费本地或云端任意文件。

URI 授权机制与持久化授权 (takePersistableUriPermission)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

从 SAF 返回的 ``content://`` URI，其本质是一个携带临时特权令牌的系统能力凭证：
1. **跨进程瞬时授权（Ephemeral Grant）**：
   - 当 DocumentsUI 将选中的 URI 通过 ``Intent`` 回传给应用 Activity 时，Intent 内部携带有 ``Intent.FLAG_GRANT_READ_URI_PERMISSION`` 或 ``FLAG_GRANT_WRITE_URI_PERMISSION``；
   - 这一标志位由系统核心服务 ``ActivityManagerService`` 内部的 ``UriGrantsManagerService`` 记录。该权限默认深度绑定在接收端 Activity 的运行周期中：一旦 Activity 被销毁，授权立即失效；
2. **持久化权限保存（Persistable URI Permission）**：
   - 对于文本编辑器、离线播放器等需要实现“最近打开文件”或长期同步外部目录的应用，必须在收到结果的第一时间显式调用权限持久化接口：

     .. code-block:: java

        // 将临时授予的 Uri 权限固化持久化至系统权限管理器中
        int takeFlags = intent.getFlags() & (Intent.FLAG_GRANT_READ_URI_PERMISSION 
                                           | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
        Uri documentUri = intent.getData();
        context.getContentResolver().takePersistableUriPermission(documentUri, takeFlags);

   - 系统将该授权项持久化至 ``/data/system/urigrants.xml`` 磁盘配置中。此后，即使手机历经多次关机重启或应用进程反复被杀死，应用依然能够直接凭此 URI 打开目标文件；
   - 只有当用户主动在系统设置中清除该应用授权、或文件所属的底层 Document Provider 明确上报该文档已被物理删除时，该持久授权才会被撤销。

Android 11 对 ACTION_OPEN_DOCUMENT_TREE 的安全收紧
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了防止恶意应用利用 ``ACTION_OPEN_DOCUMENT_TREE`` 诱导用户点击“选择整盘根目录”，从而绕过分区存储重新实现全盘扫描，Android 11 起对目录树选择施加了绝对的**红线防御机制**：
- 系统彻底屏蔽了对 **内部存储根目录（``/storage/emulated/0/``）** 的全盘授权；
- 系统彻底屏蔽了对 **下载目录根（``Download/``）** 的整目录授权；
- 系统彻底屏蔽了对 **可移除 SD 卡物理根目录** 的整目录授权；
- **核心沙箱绝对禁区**：禁止选择任何位于 ``Android/data/`` 与 ``Android/obb/`` 及其子目录下的任何路径。

用户在 DocumentsUI 界面中若尝试导航至上述敏感受限目录，系统底部的“使用此文件夹”授权按钮将直接置灰禁用，杜绝了通过用户诱导绕过沙箱的一切可能。

------------------------------------------------------------------------
41.5 Apple 平台存储沙箱与受限文件访问体系
------------------------------------------------------------------------

在 Apple 平台（iOS / iPadOS / macOS）的体系结构中，虽然没有使用“Scoped Storage”这一特定专有名词，但其在底层构建了一套更为严苛、基于内核沙箱规则扩展与能力导向的受限文件访问体系。

App Sandbox 容器标准拓扑与目录语义
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Apple 平台上每个已安装的应用均严格限制在自身的数据容器中。通过 ``FileManager`` 查询的标准目录具备高度确定性的语义和系统行为约定：

.. list-table:: Apple iOS / iPadOS 应用沙箱核心目录架构与系统行为
   :widths: 18 32 25 25
   :header-rows: 1
   :class: tight-table

   * - 容器目录名称
     - 核心存储用途
     - 是否参与系统级备份 (iCloud/iTunes)
     - 存储紧缺时是否会被系统自动清理
   * - **``Documents/``**
     - 用户生成和直接维护的文档内容
     - **是**（默认参与全量备份）
     - **否**（绝对保留，严禁系统静默擦除）
   * - **``Library/Application Support/``**
     - 应用运行支撑数据（数据库、配置文件、索引）
     - **是**（可配置排除属性）
     - **否**（属于应用关键运行资产）
   * - **``Library/Caches/``**
     - 可由算法或网络重新生成的缓存数据
     - **否**（不参与备份）
     - **是**（系统存储紧张时随时清空）
   * - **``tmp/``**
     - 短暂任务产生的临时中间计算文件
     - **否**（不参与备份）
     - **是**（应用退出或系统重启随时清理）

如果一个应用误将可重新下载的高清视频缓存写入 ``Documents/`` 目录，不仅会导致用户的 iCloud 备份空间被迅速挤爆，而且在 App Store 审核时将直接因违反数据存储指南（Data Storage Guidelines）被拒绝上架。

就地编辑 (Open-In-Place) 与临时沙箱扩展
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当用户在 iOS 上通过系统文件选择器（``UIDocumentPickerViewController``）打开一个存放在 iCloud Drive、U 盘或第三方网盘中的文档时，现代 iOS 默认采用 **Open-In-Place（就地打开编辑）** 模式：
- 应用程序并不是在自身的私有沙箱中拷贝一份副本，而是**直接获得对外部真实原始文件的实时读写权力**；
- 为了实现这一跨越容器的越界访问，iOS 内核采用了 **动态沙箱规则扩展（Dynamic Sandbox Extension）** 机制：系统内核安全模块（Seatbelt 内核扩展）在应用进程的沙箱运行态描述符中，动态追加一条临时规则，仅赋予该特定进程针对该单一文件 inode 节点的特权访问权标。

安全作用域 URL (Security-Scoped URL) 运行期生命周期
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Swift / Objective-C 运行时，代表这个被临时授权外部文件的是一个带有特殊标志位的 **``Security-Scoped URL``**。应用访问该对象必须遵循严格的**成对进入与释放生命周期模型**：

.. code-block:: swift

   // 访问外部受限文件的 Security-Scoped 生命周期治理
   func processExternalDocument(at url: URL) {
       // 步骤一: 显式请求进入安全访问作用域 (Security Scope)
       // 该调用在内核层激活针对当前进程的动态沙箱放行权标
       let accessGranted = url.startAccessingSecurityScopedResource()
       
       defer {
           // 步骤三: 必须确保在方法退出时，严格对称释放安全作用域
           // 归还系统资源，防止内核沙箱扩展表发生内存泄漏
           if accessGranted {
               url.stopAccessingSecurityScopedResource()
           }
       }
       
       guard accessGranted else {
           logger.error("内核安全作用域授权失败，用户权限已被撤销或令牌失效")
           return;
       }
       
       // 步骤二: 在受限作用域保护下，执行协调读写操作
       performCoordinatedRead(at: url)
   }

系统对单个进程同时持有的安全作用域 URL 数量设置了内核级上限配额。如果应用在读取完毕后未显式调用 ``stopAccessingSecurityScopedResource()``，将迅速耗尽沙箱扩展槽位，导致后续任何文件选择操作直接抛出拒绝访问的致命错误。

持久化访问权标：Security-Scoped Bookmark
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Security-Scoped URL 同样具有瞬时性：当应用进程被用户彻底划卡杀死或系统重启后，内存中的沙箱扩展权标瞬间湮灭。

为了支持“最近打开文档”或长期固定外部工作目录，Apple 引入了 **安全作用域书签（Security-Scoped Bookmark）** 机制：
1. **生成书签数据**：
   - 应用调用 ``url.bookmarkData(options: [.withSecurityScope], ...)``；
   - 系统将文件唯一的物理文件系统标识符（File ID / Inode）与密码学签名的沙箱权标深度结合，序列化为一段坚固的二进制 Plist 数据块（``Data``）；
   - 应用将此二进制 ``Data`` 持久化保存在自身私有的 ``Library/Application Support/`` 目录中；
2. **解析与恢复授权**：
   - 在后续任意时刻（如数周之后应用重启），应用读取该二进制数据，调用：

     .. code-block:: swift

        var isStale = false
        let resolvedURL = try URL(resolvingBookmarkData: savedBookmarkData,
                                  options: [.withSecurityScope],
                                  relativeTo: nil,
                                  bookmarkDataIsStale: &isStale)

   - 系统核验签名无误后，**在内核中重新为当前进程注入沙箱扩展权标**，并返回全新的有效 URL；
   - **Stale 过期标记自愈**：如果底层文件在此期间被用户通过 Files App 移动了存储位置、更名或挂载点变化，系统在解析书签时依然能自动追踪定位到目标 inode，但会将 ``isStale`` 标记为 ``true``。应用感知到该标记后，应当在当次访问成功后重新生成一份最新的 Bookmark 数据并覆写本地磁盘，实现持久化引用的无损自愈。

并发控制中枢：文件协调器 (NSFileCoordinator)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在多任务操作系统中，外部文件极有可能在应用编辑的同一时刻，被 iCloud 同步守护进程（``bird``）覆盖更新，或被用户在后台 Files App 中移动更名。

为了杜绝跨进程并发写入导致文件内容撕裂或元数据破坏，Apple 强制要求所有就地编辑操作必须由 **``NSFileCoordinator``（文件协调器）** 代理执行：

.. code-block:: swift

   // 基于文件协调器的安全就地写入流水线
   let coordinator = NSFileCoordinator(filePresenter: nil)
   var coordinationError: NSError?

   // 声明对目标 URL 申请原子独占写入意图
   coordinator.coordinate(writingItemAt: targetURL, options: [], error: &coordinationError) { writeURL in
       // 在此闭包内部，全系统其他试图访问该文件的进程（包含 iCloud 同步器）将被内核强制挂起
       do {
           try dataPayload.write(to: writeURL, options: .atomic)
       } catch {
           logger.error("协调写入落盘失败: \(error)")
       }
   }
   // 闭包退出后，锁立即释放，系统唤醒等待的后台同步队列，触发云端版本增量上传

通过文件协调器与文件呈现者（``NSFilePresenter``）的协同，应用还可以实时监听外部文件的移动（``presentedItemDidMoveToURL``）、外部内容变更（``presentedItemDidChange``）以及云端版本冲突（``presentedItemDidGainVersion``），构建起高度工业级的文档一致性防御状态机。

------------------------------------------------------------------------
41.6 跨平台移动存储访问模型对比与架构裁决矩阵
------------------------------------------------------------------------

至此，我们完整剖析了 Android 与 Apple 两大生态在应用存储访问治理上的底层实现。虽然双方在具体 API 命名与组织架构上存在差异，但在系统安全哲学的演进轨迹上表现出高度的一致性。

.. list-table:: Android 分区存储体系与 Apple App Sandbox 存储架构全景对比
   :widths: 16 42 42
   :header-rows: 1
   :class: tight-table

   * - 比较维度
     - Android 平台架构 (Android 11+)
     - Apple 平台架构 (iOS / iPadOS)
   * - **基础安全基座**
     - Linux UID 沙箱 + SELinux 强制类型转换
     - Darwin Mach Task 沙箱 + Seatbelt 内核扩展
   * - **私有专属存储**
     - ``filesDir`` 与 ``externalFilesDir``（免权限，卸载自毁）
     - Data Container（``Documents/``, ``Library/``, ``tmp/``）
   * - **底层虚拟化/拦截**
     - **用户态 FUSE + 内核 FUSE-BPF 硬件卸载直通**
     - **内核态 VFS 挂载隔离 + 动态 Sandbox Extension**
   * - **共享多媒体中枢**
     - **MediaStore**（基于 SQLite 的结构化元数据中心与 URI 操作）
     - **PhotoKit / PHPhotoLibrary**（系统私有数据库与精细资产授权）
   * - **通用非媒体文档**
     - **Storage Access Framework (SAF) + DocumentsUI**
     - **Document Picker / Browser + Open-In-Place**
   * - **授权令牌形态**
     - ``content://`` URI 结合系统 ``UriPermissionGrant``
     - 带有内核权标的 ``Security-Scoped URL``
   * - **授权持久化方案**
     - ``takePersistableUriPermission()``（写入 XML 登记表）
     - ``Security-Scoped Bookmark``（密码学签名二进制 Plist）
   * - **并发冲突控制**
     - 应用自行处理并发，或依赖 ContentProvider 事务
     - **内核/服务级 ``NSFileCoordinator`` 与 ``NSFilePresenter``**
   * - **全盘文件访问特权**
     - ``MANAGE_EXTERNAL_STORAGE``（仅限特许工具，商店强审）
     - **无（绝对禁止第三方 App 获取全盘文件系统访问权）**

移动存储架构选型工程裁决决策树
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于面向双平台开发的移动系统架构师与高级工程师，在面对一个具体的文件写入与存储需求时，应当严格遵循如下决策流：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                现代移动应用存储路径工程裁决决策树                       |
   +-------------------------------------------------------------------------+
   [起点: 业务产生了一笔新的数据或文件]
          |
          v
   <决策点 1: 该数据是否仅服务于本应用自身内部运行？>
          |
          +---> [是: 属于应用专属数据]
          |       |
          |       v
          |     <决策点 2: 卸载或系统清理时，用户是否接受该数据被同步删除？>
          |            |
          |            +---> [是: 可重建或私有运行文件]
          |            |       |
          |            |       +---> [小文件/数据库/配置]: 内部私有存储 (filesDir / Documents)
          |            |       +---> [体积较大/可重新下载]: 缓存目录 (cacheDir / Caches)
          |            |
          |            +---> [否: 核心用户成果，要求永久保留]
          |                    |
          |                    v (强制转向公共共享通道)
          |
          +---> [否: 属于用户跨应用共享资产或需要长期持久化保存的独立成果]
                  |
                  v
          <决策点 3: 目标文件的数据类型究竟是什么？>
                  |
                  +---> [图片 / 视频 / 音频文件]
                  |       |
                  |       v
                  |     【标准多媒体中枢路径】:
                  |       - Android: 写入 MediaStore 对应集合 (利用 IS_PENDING 状态机)
                  |       - iOS: 使用 PhotoKit 将资产写入系统相册 (PHPhotoLibrary)
                  |
                  +---> [文档 / 压缩包 / 代码 / 任意格式导出文件]
                          |
                          v
                        【显式用户意志主导路径】:
                          - 导入已有文档: Android 调用 ACTION_OPEN_DOCUMENT; 
                                          iOS 调用 UIDocumentPickerViewController
                          - 导出新文件:   Android 调用 ACTION_CREATE_DOCUMENT; 
                                          iOS 调用就地导出或文件协调写入
                          - 长期打开恢复: Android 调用 takePersistableUriPermission();
                                          iOS 生成并持久化 Security-Scoped Bookmark

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章我们系统解构了现代移动操作系统的存储访问模型与受限存储框架：
- 剖析了早期外部存储因为 FAT32 物理设计缺陷与全局读写权限泛滥，引发的公有目录污染、隐蔽跨应用追踪信道与隐私失守危机；
- 深入拆解了 Android 分区存储（Scoped Storage）的四层空间划分模型，揭秘了从用户态 FUSE、内核态 sdcardfs 到现代 FUSE + FUSE-BPF 硬件卸载的虚拟文件系统演进脉络；
- 解构了 MediaStore 集中式多媒体中枢的架构，推导了 ``IS_PENDING`` 两阶段提交原子保护、修改他人媒体的 RecoverableSecurityException 提权机制、Android 13 精细化媒体权限及零权限 Photo Picker 运行原理；
- 系统拆解了通用文档的存储访问框架（SAF），深入 Document Provider 虚拟树形接口、URI 授权机制与 ``takePersistableUriPermission()`` 持久化恢复原理，以及 Android 11 对敏感根目录的红线限制；
- 全景剖析了 Apple 平台的存储沙箱（App Sandbox）架构，推导了基于动态内核扩展的 Security-Scoped URL 生命周期、基于密码学签名的 Security-Scoped Bookmark 持久化自愈模型，以及基于 ``NSFileCoordinator`` 的跨进程并发安全保护；
- 建立了双平台存储访问模型的完整对比矩阵，给出了工业级移动存储路径架构选型决策树。

至此，移动操作系统在**静态物理存储**（F2FS、FBE、ICE）与**动态文件访问权限**（Scoped Storage、SAF、App Sandbox）两个层面均已构筑起坚不可摧的工程防线。

然而，在移动设备有限的电池物理容量（3000~5000 mAh）与全天候联网待机需求面前，仅仅管理好存储还远远不够。如果应用程序在后台肆意保持 CPU 唤醒锁（WakeLock）、滥用高频无序定时器、在后台不断发起未经节制的网络轮询与广播拉活，整机的电量储备将在数小时内迅速耗尽，手机将严重发热并陷入低电瘫痪。

在接下来的 **Chapter 42: 功耗与后台执行治理：Doze 模式、App Standby 与 iOS BGTask**（也是本书全书的终局收官之作）中，我们将深入移动电源管理子系统的最底层：系统解构 Android 系统的 Doze 模式状态机、应用待机分组（App Standby Buckets）与后台网络限制策略，深入 Apple 平台的后台任务调度框架（BGTaskScheduler）、内存挂起（Suspension）与对齐执行机制，全面揭示移动操作系统如何在保障用户前台丝滑流畅与关键通知实时触达的同时，将整机待机静态电流极致压榨至微安级的终极系统工程！
