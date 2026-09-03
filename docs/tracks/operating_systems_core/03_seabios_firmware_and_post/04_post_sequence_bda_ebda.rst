========================================================================================
第 4 节：POST (Power-On Self-Test) 加电自检时序、BDA (0x400) 与 EBDA 内存拓扑建立
========================================================================================

.. note::
   **前置背景与上下文承接**
   * **体系结构基准**：承接模块 03 第 3 节中关于主板 PAM 寄存器解锁、将 1MB 顶部 Shadow ROM 区域原子切换为可读写物理 DRAM 的微观机制。
   * **核心使命**：解构主板固件在获得可写内存后，如何执行完整的加电自检（POST）全局调度流水线；深入剖析 x86 传统 1MB 实模式物理内存中的三大核心控制中枢——**中断向量表 (IVT, 0x00000)**、**BIOS 数据区 (BDA, 0x00400)** 与 **扩展 BIOS 数据区 (EBDA, 0x9FC00 附近)** 的物理内存拓扑与字段级结构；深入 SeaBIOS 源码 ``src/post.c`` 与 ``src/std/bda.h``，逐行解构串口/并口基址、键盘环形缓冲队列、显卡参数矩阵、时钟滴答计数器（``timer_counter``）以及向引导加载器与操作系统传递底层硬件配置的物理全流程。

----------------------------------------------------------------------------------------

第一幕：POST (Power-On Self-Test) 加电自检总体调度流水线
--------------------------------------------------------

在 SeaBIOS 源码库（``/Volumes/LinuxKernel/seabios``）中，加电自检（POST）是整个固件生命周期中最庞大的总控引擎。在 ``src/post.c`` 中，POST 流水线被划分为严谨的五个阶段：

::

   [CPU 上电复位 / reset_vector]
                 │
                 ▼ transition32 跃迁进入 32 位保护模式
   [阶段 1：早期不可变预初始化 (handle_post -> dopost)]
   - serial_debug_preinit(): 快速初始化 0x3F8 串口输出调试日志
   - make_bios_writable(): 配置 PAM 寄存器，将 0xF0000 变为可写 Shadow RAM
   - qemu_preinit() / malloc_preinit(): 探测内存大小并初始化临时堆分配器
                 │
                 ▼ reloc_preinit()
   [阶段 2：初始化代码自重定位 (Code Relocation)]
   - 在动态堆中分配临时执行空间: codedest = memalign_tmp(codealign, initsize)
   - 将 post.c 初始化代码段从只读 ROM 复制到临时 RAM 堆区
   - updateRelocs(): 扫描并修复绝对地址与相对地址重定位表项
   - 转移控制权至重定位后的 maininit() 运行
                 │
                 ▼ maininit() -> interface_init()
   [阶段 3：核心接口与物理内存中枢建立]
   - malloc_init(): 建立最终的低端与高端物理内存分配器
   - qemu_cfg_init(): 解析 QEMU fw_cfg 虚拟通道，读取 CPU 核心数与引导参数
   - ivt_init(): 在 0x00000 处初始化 256 个实模式中断向量表项
   - bda_init(): 在 0x00400 处建立 256 字节 BIOS 数据区 (BDA)
   - 划分并在常规内存顶端建立 EBDA (Extended BIOS Data Area)
                 │
                 ▼ platform_hardware_setup() + device_hardware_setup()
   [阶段 4：平台芯片组与外部总线设备探测]
   - pic_setup() / timer_setup(): 初始化 8259A 中断控制器与 8254 定时器
   - thread_setup(): 启动固件协同多线程环境
   - pci_setup(): 递归扫描 PCI/PCIe 总线树，分配 BAR 物理地址 (详见第 5 节)
   - vgarom_setup() / optionrom_setup(): 扫描并执行板载显卡与外部扩展卡 Option ROM
                 │
                 ▼ prepareboot() -> startBoot()
   [阶段 5：引导装载准备与控制权移交]
   - cdrom_prepboot() / e820_prepboot(): 冻结最终 E820 内存图
   - make_bios_readonly(): 执行 wbinvd 并重新锁定 PAM 寄存器为只读
   - startBoot(): 触发 INT 19h 软中断，加载磁盘 MBR 引导扇区 (0x7C00)

----------------------------------------------------------------------------------------

第二幕：低端 1MB 内存布局黄金拓扑——IVT, BDA 与 EBDA
---------------------------------------------------

在操作系统接管计算机之前，整个 x86 计算机的全部运行状态均由物理内存前 1MB（``0x00000000 ~ 0x000FFFFF``）维系。这是计算机体系结构史上最著名的 **传统实模式内存黄金拓扑**：

::

   物理内存绝对地址 (GPA)
   0x00000000 ┌────────────────────────────────────────────────────────┐
              │ 中断向量表 (IVT, 1024 字节 = 256 个 segoff_s 向量)      │ ◄── ivt_init() 建立
   0x00000400 ├────────────────────────────────────────────────────────┤
              │ BIOS 数据区 (BDA, 256 字节, 0x400 ~ 0x4FF)             │ ◄── bda_init() 建立
   0x00000500 ├────────────────────────────────────────────────────────┤
              │ 传统 DOS / 固件临时变量与临时堆栈 (0x500 ~ 0x7BFF)      │
   0x00007000 ├────────────────────────────────────────────────────────┤
              │ SeaBIOS 早期调用栈 (BUILD_STACK_ADDR)                  │
   0x00007C00 ├────────────────────────────────────────────────────────┤
              │ MBR 引导扇区装载物理锚点 (Boot Sector, 512 字节)        │ ◄── INT 19h 目标读取地址
   0x00007E00 ├────────────────────────────────────────────────────────┤
              │                                                        │
              │ 自由常规物理内存 (Free Conventional Memory, ~600KB)    │
              │                                                        │
   0x0009FC00 ├────────────────────────────────────────────────────────┤ ◄── get_ebda_ptr() (动态边界)
              │ 扩展 BIOS 数据区 (EBDA, 通常 1KB ~ 128KB)               │ ◄── BDA 记录其段基址 0x9FC0
   0x000A0000 ├────────────────────────────────────────────────────────┤ (640KB 常规内存上限)
              │ VGA 显卡显示显存 (VRAM, 128KB, 0xA0000 ~ 0xBFFFF)       │
   0x000C0000 ├────────────────────────────────────────────────────────┤
              │ 显卡与扩展设备 Option ROM 区域 (192KB, 0xC0000~0xEFFFF)│
   0x000F0000 ├────────────────────────────────────────────────────────┤
              │ 主系统 BIOS 固件常驻段 (Shadow RAM, 64KB, 0xF0000..0xFFFFF)
   0x00100000 └────────────────────────────────────────────────────────┘ (1MB 物理边界 / High Memory 起点)

2.1 为什么 EBDA 必须动态锚定在常规内存顶端（0x9FC00 附近）？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **向后兼容防踩踏**：历史上 DOS 与早期操作系统假定常规内存从 ``0x00000`` 开始向上生长。如果将固件扩展数据放置在低端内存，会被操作系统加载程序直接覆盖；
* **基内存欺骗机制**：SeaBIOS 将 EBDA 放置在常规内存的最高端（紧邻 ``0xA0000`` 显存下方，如 ``0x9FC00``），并在 BDA 中向软件宣告“系统基内存仅有 639KB（``mem_size_kb = 639``）”。操作系统读取该字段后，自动将 ``0x9FC00 ~ 0x9FFFF`` 视为硬件保留区域，绝不向其分配内存，从而为 BIOS 提供了绝对安全的常驻数据存储空间。

----------------------------------------------------------------------------------------

第三幕：BIOS 数据区 (BDA, 0x00400) 核心字段微观解构
---------------------------------------------------

**BIOS Data Area (BDA)** 固定位于物理地址 ``0x00000400 ~ 0x000004FF``（段基址 ``SEG_BDA = 0x0040``，偏移 ``0x0000``），共占用 256 字节。

在 ``src/std/bda.h`` 中，``struct bios_data_area_s`` 的物理内存字段排布如下：

::

   +-----------------------------------------------------------------------------------+
   |                       struct bios_data_area_s (256 字节内存布局)                  |
   |                                                                                   |
   |  偏移地址    字段名称                    类型     硬件功能与物理语义              |
   +===================================================================================+
   |  0x40:00     port_com[4]                 u16[4]   COM1~COM4 串口 I/O 端口基地址   |
   |                                                   (典型值: 0x3F8, 0x2F8, 0x3E8, 0x2E8)
   |  0x40:08     port_lpt[3]                 u16[3]   LPT1~LPT3 并口 I/O 端口基地址   |
   |  0x40:0E     ebda_seg                    u16      EBDA 扩展数据区 16 位段基址     |
   |                                                   (典型值: 0x9FC0 -> 物理 0x9FC00)|
   |  0x40:10     equipment_list_flags        u16      硬件设备清单标志位字 (软驱/显卡)|
   |  0x40:13     mem_size_kb                 u16      常规内存总容量 (以 KB 计, 639)  |
   |  0x40:17     kbd_flag0                   u16      键盘 Shift/Ctrl/Alt 状态位图    |
   |  0x40:1A     kbd_buf_head                u16      键盘环形缓冲区头指针 (相对 0x40)|
   |  0x40:1C     kbd_buf_tail                u16      键盘环形缓冲区尾指针 (相对 0x40)|
   |  0x40:1E     kbd_buf[32]                 u8[32]   键盘 16 个键码环形存储队列      |
   |  0x40:49     video_mode                  u8       当前 VGA 显示模式 (如 0x03 文本)|
   |  0x40:4A     video_cols                  u16      当前屏幕文本列数 (如 80 列)     |
   |  0x40:4C     video_pagesize              u16      当前显示页面字节大小 (如 4096)  |
   |  0x40:4E     video_pagestart             u16      当前显示页面显存起始偏移        |
   |  0x40:50     cursor_pos[8]               u16[8]   8 个显示页面的光标行列坐标      |
   |                                                   (高字节=Row 行号, 低字节=Col 列号)
   |  0x40:60     cursor_type                 u16      光标扫描线形状 (起始/结束扫描线)|
   |  0x40:62     video_page                  u8       当前活动显示页面编号 (0..7)     |
   |  0x40:63     crtc_address                u16      CRTC 显示控制器 I/O 端口 (0x3D4)|
   |  0x40:6C     timer_counter               u32      时钟滴答计数器 (每秒累加 18.2次)|
   |  0x40:70     timer_rollover              u8       时钟跨天回绕标志 (满 24小时置 1)|
   |  0x40:75     hdcount                     u8       系统检测到的物理硬盘总数量      |
   +-----------------------------------------------------------------------------------+

3.1 键盘环形缓冲队列（Circular Buffer）的硬件读写
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当用户在键盘上敲下一个按键时，键盘硬件产生 IRQ 1 中断，触发 BIOS ``INT 09h`` 中断服务程序：
1. 8042 键盘控制器读取扫描码并翻译为 ASCII 码；
2. ``INT 09h`` 检查 BDA 中的 ``kbd_buf_tail``；
3. 计算下一个写入位置：$	ext{Next\_Tail} = (	ext{kbd\_buf\_tail} == 0	ext{x3E}) \ ? \ 0	ext{x1E} : (	ext{kbd\_buf\_tail} + 2)$；
4. 若 $	ext{Next\_Tail} 
e 	ext{kbd\_buf\_head}$（缓冲区未满），将按键键码写入 ``0x40:kbd_buf_tail``，并将 ``kbd_buf_tail`` 更新为 ``Next_Tail``；
5. 当应用程序调用 ``INT 16h`` 读取键盘时，BIOS 从 ``kbd_buf_head`` 提取字符并推进头指针。

3.2 8254 时钟滴答计数器：``timer_counter``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
物理定时器 8254 Channel 0 每隔约 $54.925	ext{ ms}$（频率 $18.2065	ext{ Hz}$）产生一次 IRQ 0 中断，触发 ``INT 08h``：
* ``INT 08h`` 中断服务程序自动将物理内存 ``0x0000046C`` 处的 32 位整数 ``timer_counter`` 累加 1；
* 当该数值达到一整天的滴答总数时：

.. math::

   	ext{TICKS\_PER\_DAY} = 18.20648 	imes 3600 	imes 24 = 1573040 \quad (0	ext{x1800B0})

* BIOS 自动将 ``timer_counter`` 清零，并将 ``0x40:70 (timer_rollover)`` 标志位置 1，供 DOS / BIOS 读取系统日期时实现自动跨天加 1。

----------------------------------------------------------------------------------------

第四幕：扩展 BIOS 数据区 (EBDA) 与现代硬件数据锚定
--------------------------------------------------

随着 PS/2 鼠标、高级电源管理（APM）、多处理器规范（MP Table）与 ACPI 体系的引入，256 字节的 BDA 空间彻底告罄。为此引入了 **EBDA (Extended BIOS Data Area)**。

4.1 EBDA 初始化与 E820 内存保留时序（``bda_init()``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 ``src/post.c:bda_init()`` 中：

::

   static void bda_init(void) {
       struct bios_data_area_s *bda = MAKE_FLATPTR(SEG_BDA, 0);
       memset(bda, 0, sizeof(*bda));

       int esize = EBDA_SIZE_START; /* 初始通常为 1KB */
       u16 ebda_seg = EBDA_SEGMENT_START; /* 0x9FC0 */
       
       // 1. 将 EBDA 段基址写入 BDA 0x40:0x0E
       SET_BDA(ebda_seg, ebda_seg);

       // 2. 将扣除 EBDA 后的常规内存大小写入 BDA 0x40:0x13
       SET_BDA(mem_size_kb, ebda_seg / (1024 / 16)); /* 0x9FC0 / 64 = 639 KB */

       // 3. 初始化 EBDA 结构体本身
       struct extended_bios_data_area_s *ebda = get_ebda_ptr();
       memset(ebda, 0, sizeof(*ebda));
       ebda->size = esize; /* 记录 EBDA 自身大小为 1KB */

       // 4. 将 EBDA 物理内存区间在 E820 内存图中硬性注册为 E820_RESERVED!
       e820_add((u32)ebda, BUILD_LOWRAM_END - (u32)ebda, E820_RESERVED);

       // 5. 初始化 ExtraStack 栈底指针
       StackPos = &ExtraStack[BUILD_EXTRA_STACK_SIZE] - SYMBOL(zonelow_base);
   }

4.2 EBDA 内部结构与现代高级数据结构锚定
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 ``src/std/bda.h`` 中，``struct extended_bios_data_area_s`` 包含了：
* **偏移 0x00**：``u8 size``（EBDA 大小，以 KB 为单位）；
* **偏移 0x22**：``far_call_pointer``（用于 16 位受保护远调用的入口指针）；
* **偏移 0x26 ~ 0x2F**：PS/2 鼠标数据包接收队列与状态机；
* **偏移 0x3D**：软盘物理参数表（``struct fdpt_s fdpt[2]``）；
* **偏移 0x121 起始的自定义扩展区**：
  * 存放 **ACPI RSDP (Root System Description Pointer)** 结构体（使 64 位操作系统内核启动时能在低端 1MB 内存中扫描到 ``"RSD PTR "`` 签名！）；
  * 存放 **Intel MP Table (多处理器配置表)**，为不支持 ACPI 的老旧内核提供 CPU 拓扑与 APIC 映射。

----------------------------------------------------------------------------------------

第五幕：中断向量表 (IVT, 0x00000) 初始化与中断挂载
--------------------------------------------------

在物理内存的最底部 ``0x00000000 ~ 0x000003FF``（共 1024 字节），驻留着 256 个 16 位实模式中断向量。每个向量占用 **4 字节**，格式为 ``Offset (2 字节) : Segment (2 字节)``。

在 ``src/post.c:ivt_init()`` 中，SeaBIOS 执行了防御性与功能性并重的中断挂载流水线：

::

   static void ivt_init(void) {
       // 1. 防御性初始化：将全部 256 个向量先默认指向统一的 entry_iret_official
       //    该处理函数仅有一条机器指令: iretw (空中断返回)，防止外设产生未注册中断时 CPU 跑飞
       for (int i = 0; i < 256; i++)
           SET_IVT(i, FUNC16(entry_iret_official));

       // 2. 挂载 16 个硬件 PIC 中断处理跳板
       for (int i = BIOS_HWIRQ0_VECTOR; i < BIOS_HWIRQ0_VECTOR + 8; i++)
           SET_IVT(i, FUNC16(entry_hwpic1)); // IRQ 0..7 对应 Vector 0x08..0x0F
       for (int i = BIOS_HWIRQ8_VECTOR; i < BIOS_HWIRQ8_VECTOR + 8; i++)
           SET_IVT(i, FUNC16(entry_hwpic2)); // IRQ 8..15 对应 Vector 0x70..0x77

       // 3. 挂载核心标准 BIOS 软件服务接口
       SET_IVT(0x02, FUNC16(entry_02));            // NMI 不可屏蔽中断
       SET_IVT(0x10, FUNC16(entry_10));            // INT 10h: VGA 显示与文本输出服务
       SET_IVT(0x12, FUNC16(entry_12));            // INT 12h: 获取常规内存大小 (返回 639KB)
       SET_IVT(0x13, FUNC16(entry_13_official));   // INT 13h: 磁盘/软盘块设备读写服务
       SET_IVT(0x15, FUNC16(entry_15_official));   // INT 15h: 系统扩展服务 (E820 内存探测)
       SET_IVT(0x16, FUNC16(entry_16));            // INT 16h: 键盘输入服务
       SET_IVT(0x19, FUNC16(entry_19_official));   // INT 19h: 引导加载中断 (Bootstrap Loader)
       SET_IVT(0x1A, FUNC16(entry_1a_official));   // INT 1Ah: PCI-BIOS 与 RTC 时间服务
   }

至此，低端 1MB 内存的全部神经中枢（IVT 处理函数、BDA 硬件状态、EBDA 扩展指针）全部构筑完毕。

----------------------------------------------------------------------------------------

小结与下章导读
--------------

本节系统化剖析了 SeaBIOS 的 POST 全局自检调度流水线，深入解构了物理内存 ``0x00000`` 处的中断向量表（IVT）、``0x00400`` 处的 BIOS 数据区（BDA）以及 ``0x9FC00`` 处的扩展数据区（EBDA）的微观字段物理拓扑。

固件核心数据结构建立后，主板必须面向外部物理总线，探测机箱内插入的所有 PCI/PCIe 设备（网卡、显卡、磁盘控制器）并为它们分配物理内存与中断。

在 **第 5 节：PCI 总线递归扫描、BAR 空间物理地址分配与 Option ROM 扩展卡固件调用** 中，我们将深入剖析 SeaBIOS 的 PCI 总线递归扫描引擎，解构固件如何动态计算每个设备的 BAR 空间大小并分配不冲突的 32 位系统物理地址，以及如何将第三方显卡/网卡的 Option ROM 固件调入内存执行。
