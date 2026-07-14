第十四章：SeaBIOS 怎样执行 QEMU 的 ACPI table-loader 并找到 RSDP？
================================================================

上一章结束时，SeaBIOS 已经安装 PIRQ、MP table 与 SMBIOS。控制流仍在：

::

   qemu_platform_setup()

下一段源码是：

.. code-block:: c

   if (CONFIG_FW_ROMFILE_LOAD) {
       loader_err = romfile_loader_execute("etc/table-loader");
       RsdpAddr = find_acpi_rsdp();
       ...
   }

这一段容易被概括成“加载 ACPI 表”。实际发生的事情更接近一次小型动态链接：QEMU 先准备表的原始字节、RSDP 和一串重定位命令；SeaBIOS 再决定这些字节放进客户机物理内存的什么位置，修正表与表之间的指针，重新计算 checksum，最后从低端固件区找到 ACPI 的入口 RSDP。

本章固定使用：

::

   SeaBIOS commit c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   QEMU commit    a759542a2c62f0fd3b65f5a66ad9868201014669

本章结束在 ``find_acpi_rsdp()`` 成功返回。下一章再沿 RSDP 进入 RSDT/XSDT、FADT、MADT 和 DSDT。

ACPI 表的内容由 QEMU 生成，最终地址由 SeaBIOS 决定
-------------------------------------------------

在当前 QEMU q35 路径中，现代 ACPI 表并不是 SeaBIOS 从零硬编码出来的。QEMU 比客户机 CPU 更早知道虚拟机的完整硬件模型，例如：

* 创建了多少 vCPU；
* local APIC 与 I/O APIC 怎样呈现；
* q35 PCI host bridge 和 ICH9 LPC 位于哪里；
* SCI、PM timer、reset register 使用哪些端口；
* 是否存在 HPET、TPM、NUMA、热插拔设备或 virtio-mmio；
* PCI 路由和 AML namespace 应怎样描述。

因此 QEMU 在宿主机进程中生成 ACPI table blob，再通过 ``fw_cfg`` 暴露给 SeaBIOS。关键文件名由 QEMU 头文件固定：

::

   etc/acpi/tables
   etc/acpi/rsdp
   etc/table-loader
   etc/tpm/log          条件存在

``etc/acpi/tables``
   保存 RSDT/XSDT 所指向的主要表及 AML 数据。

``etc/acpi/rsdp``
   保存 Root System Description Pointer。它必须放到传统固件搜索范围，使仍按 PC 固件规则工作的软件能够找到它。

``etc/table-loader``
   不是 ACPI 表本身，而是一串告诉固件怎样分配、链接和校验前两个 blob 的命令。

``etc/tpm/log``
   只有虚拟机提供相应 TPM measured-boot 配置时才出现。它可能也由 loader 分配，并被 TPM2 或 TCPA 表指向。

这里形成一个明确分工：

::

   QEMU
      生成机器描述和未完成链接的表字节

   SeaBIOS
      在客户机地址空间分配最终位置
      → 按命令修正地址
      → 计算最终 checksum
      → 公布 RSDP

为什么 QEMU 不能事先把所有物理指针写死
---------------------------------

ACPI 表包含大量物理地址关系，例如：

::

   RSDP → RSDT / XSDT
   RSDT / XSDT → FADT、MADT、MCFG、HPET、TPM2 ...
   FADT → FACS
   FADT → DSDT

QEMU 生成 blob 时，还不能简单假设 SeaBIOS 一定会把 ``etc/acpi/tables`` 放在某个固定客户机物理地址。最终位置受以下因素影响：

* 当前 ``ZoneHigh`` 与 ``ZoneFSeg`` 的剩余空间；
* 表的大小和对齐要求；
* 其他固件表和永久分配已经占用的区域；
* 某些入口结构必须放在低于 1 MiB 的传统可搜索区域；
* 某些大表适合放在高端 RAM。

如果先把地址写死，SeaBIOS 一旦选择不同位置，表中的所有指针都会失效。QEMU 因此把指针字段先写成“源 blob 内偏移”，再让 SeaBIOS 在完成分配后加上真实基址。

table-loader 是固定大小命令数组
---------------------------

QEMU 的 ``BiosLinkerLoaderEntry`` 由一个 32 位 command 和一个填充到 124 字节的 union 构成，所以每条命令固定占 128 字节。

SeaBIOS 执行：

.. code-block:: c

   data = romfile_loadfile("etc/table-loader", &size);

随后先检查：

.. code-block:: c

   size % sizeof(*entry) == 0

这保证整个文件可以完整切分为命令记录。然后它按 128 字节步长顺序解释：

::

   ALLOCATE
   ADD_POINTER
   ADD_CHECKSUM
   WRITE_POINTER

未知 command 会被跳过，而不是直接把整个启动过程判为失败。这给接口保留了向后兼容空间：较新的 QEMU 可以增加旧 SeaBIOS 不认识、但并非当前启动必需的命令。

ALLOCATE：先把 blob 放进客户机内存
--------------------------------

``ROMFILE_LOADER_COMMAND_ALLOCATE`` 携带：

::

   file
   align
   zone

SeaBIOS 首先验证 ``align`` 是 2 的幂，然后把最小对齐提高到固件分配器要求的 ``MALLOC_MIN_ALIGN``。

zone 只有两种受支持选择：

``ROMFILE_LOADER_ALLOC_ZONE_HIGH``
   从 ``ZoneHigh`` 分配。这里适合体积较大的 ACPI table blob 和其他不要求传统低端搜索的对象。

``ROMFILE_LOADER_ALLOC_ZONE_FSEG``
   从 ``ZoneFSeg`` 分配。RSDP 等需要被传统固件扫描规则发现的小型入口结构放在这里。

随后 SeaBIOS：

.. code-block:: c

   file->file = romfile_find(entry->alloc.file);
   data = _malloc(zone, file->file->size, alloc_align);
   file->file->copy(file->file, data, file->file->size);

这三步分别表示：

#. 在 ``romfile`` 名字空间中找到对应 fw_cfg 文件；
#. 在客户机物理内存中分配最终存放位置；
#. 把 QEMU 提供的原始 blob 复制进去。

loader 会记录：

::

   文件名
   原始 romfile 元数据
   客户机中的最终 data 地址

后续指针修正都通过这张运行期映射表，把“文件名”解析成“最终客户机物理地址”。

为什么所有 ALLOCATE 命令必须最先执行
--------------------------------

QEMU 生成命令时，会把 ALLOCATE 记录 prepend 到 command blob 前部。原因不是格式习惯，而是链接依赖：

::

   在修正 A → B 的指针之前
   A 与 B 都必须已经拥有最终地址

如果先出现 ADD_POINTER，而目标或源文件尚未分配，SeaBIOS 无法知道应加上的基址，只能报内部错误。

所以命令流逻辑上分两阶段：

::

   第一阶段：为所有 blob 确定最终客户机地址
   第二阶段：修正指针、checksum 和回写字段

ADD_POINTER：把 blob 内偏移变成真实物理地址
---------------------------------------

``ROMFILE_LOADER_COMMAND_ADD_POINTER`` 指定：

::

   dest_file
   src_file
   offset
   size

它的语义是：读取 ``dest_file`` 中 ``offset`` 位置的 1、2、4 或 8 字节小端整数，把 ``src_file`` 的最终客户机基址加进去，再把结果写回原字段。

假设 QEMU 在 XSDT 某项中预先写入：

::

   0x0000000000002400

这个值表示目标表位于 ``etc/acpi/tables`` blob 内 offset ``0x2400``。SeaBIOS 最终把整个 blob 分配到：

::

   tables_base = 0x7fe0000

修正后字段变成：

::

   0x07fe0000 + 0x2400 = 0x07fe2400

于是 XSDT 中不再是“文件内偏移”，而是 CPU 可以直接访问的客户机物理地址。

SeaBIOS 对每次修正都检查：

* 源文件和目标文件都已经分配；
* offset 加 size 没有整数回绕；
* 字段没有越过目标 blob；
* size 必须是 1、2、4 或 8；
* 最终地址能装进指定字段宽度。

这些检查防止损坏的 loader 命令把地址写出 ACPI blob。

ADD_CHECKSUM：地址改完以后重新闭合校验和
------------------------------------

ACPI 表头包含 8 位 checksum。规范要求指定范围内所有字节相加后，低 8 位为零：

::

   sum(table bytes) mod 256 = 0

指针字段被 ADD_POINTER 修改以后，QEMU 生成 blob 时预先计算的 checksum 已经失效。因此 checksum 命令必须位于相关指针修正之后。

SeaBIOS 执行：

.. code-block:: c

   *checksum_byte -= checksum(file->data + start, length);

假设当前所有字节之和低 8 位是 ``0x35``，checksum byte 就减去 ``0x35``。修改后再次求和，低 8 位变成零。

这不是密码学完整性保护。它只能检测常见的字节损坏、长度错误或未完成重定位，不能抵抗恶意修改。

WRITE_POINTER：把客户机地址反向写回 QEMU
------------------------------------

``ROMFILE_LOADER_COMMAND_WRITE_POINTER`` 与 ADD_POINTER 的方向不同。

ADD_POINTER 修改的是已经装进客户机 RAM 的 ACPI blob；WRITE_POINTER 则通过 fw_cfg DMA，把某个已分配对象的客户机物理地址写回 QEMU 暴露的另一个 fw_cfg 文件。

SeaBIOS 计算：

::

   pointer = src_file guest base + src_offset

然后调用：

.. code-block:: c

   qemu_cfg_write_file(...)

成功以后，它还把 key、offset、pointer size 和值保存进 ``romfile_pointer_list``。后续固件 resume 路径可以调用 ``romfile_fw_cfg_resume()``，重新把这些地址写回 QEMU，避免恢复后 QEMU 仍持有过期的客户机指针。

这条命令要求 fw_cfg DMA 写能力，普通只读端口访问无法完成反向写入。

SeaBIOS 顺序执行命令，不再做第二轮链接
---------------------------------

``romfile_loader_execute()`` 的主循环只有一遍：

.. code-block:: c

   for each entry:
       switch command:
           ALLOCATE
           ADD_POINTER
           ADD_CHECKSUM
           WRITE_POINTER

因此 QEMU 必须保证命令顺序已经满足依赖关系。SeaBIOS 不是通用 ELF linker，不会分析符号图，也不会为了等待依赖而重新排序。

执行成功返回零，表示命令文件格式可执行且主循环走完。单个可选文件缺失时，某些 allocate 可以直接不产生对象；严重的格式、越界或分配问题会发出固件警告。返回零也不自动证明 RSDP 一定已经正确安装，所以调用者紧接着还要主动搜索。

find_acpi_rsdp 不是读取一个全局变量
--------------------------------

loader 返回后，``qemu_platform_setup()`` 执行：

.. code-block:: c

   RsdpAddr = find_acpi_rsdp();

SeaBIOS 没有直接相信“RSDP 应该在某个预定地址”，而是在最终 ``ZoneFSeg`` 范围内按 16 字节边界扫描：

::

   ALIGN(zonefseg_start, 16)
   → 每次增加 16
   → 直到 zonefseg_end

16 字节对齐来自 ACPI 对 RSDP 搜索的传统要求，也能避免逐字节遍历整段 F-segment。

每个候选位置必须先通过 ``get_acpi_rsdp_length()``。

第一层验证是固定 20 字节部分：

* signature 必须是 ``"RSD PTR "``；
* 候选区域至少容纳 20 字节；
* 前 20 字节 checksum 必须为零。

如果 revision 大于 1，还要继续：

* 读取 RSDP 自带的 length；
* 确认 length 没有越过扫描区尾端；
* 验证整个扩展 RSDP checksum。

只有两段验证都通过，函数才返回该物理地址。

为什么 revision 2 仍要保留前 20 字节 checksum
----------------------------------------

ACPI 2.0 以后，RSDP 增加了：

::

   length
   xsdt_physical_address
   extended_checksum

但它没有删除 ACPI 1.0 的前 20 字节布局。旧软件可能只理解 RSDT 字段，所以新版 RSDP 同时维持：

::

   checksum           覆盖前 20 字节
   extended_checksum  覆盖整个 RSDP

SeaBIOS 的验证顺序正好反映这个兼容设计。

找到 RSDP 后，ACPI 才真正拥有入口
-----------------------------

在 ``find_acpi_rsdp()`` 返回前，表 blob 即使已经放进 RAM，也只是一些彼此链接的结构。找到并保存：

.. code-block:: c

   RsdpAddr

以后，SeaBIOS、bootloader 和 Linux 才拥有统一入口去遍历整张 ACPI 表图。

它们不需要知道 QEMU 的 fw_cfg 文件名，也不需要理解 ``table-loader``。对后续软件来说，QEMU 与 SeaBIOS 的协作痕迹已经被隐藏，剩下的是标准 ACPI 结构：

::

   RSDP
   ├── RSDT
   └── XSDT
       ├── FADT
       ├── MADT
       ├── MCFG
       ├── HPET
       ├── TPM2 / TCPA
       └── 其他条件表

第十四章结束时的机器状态
----------------------

控制权目前走过：

::

   qemu_platform_setup()
   → smbios_setup() 返回
   → romfile_loader_execute("etc/table-loader")
   → 从 fw_cfg 读取 128 字节命令记录
   → ALLOCATE：把 ACPI blobs 分配到 ZoneHigh / ZoneFSeg
   → ADD_POINTER：把 blob 内偏移修正为客户机物理地址
   → ADD_CHECKSUM：重新计算 ACPI checksum
   → 条件 WRITE_POINTER：通过 fw_cfg DMA 把地址写回 QEMU
   → loader 返回
   → find_acpi_rsdp()
   → 16 字节对齐扫描 F-segment
   → 验证 RSDP signature 与两层 checksum
   → RsdpAddr 保存成功

此刻：

* 当前执行者：SeaBIOS ``qemu_platform_setup()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* AP：已完成固件报到并停在 ``HLT``；
* ACPI table blob：已复制到最终客户机内存；
* 表间物理指针：已修正；
* ACPI checksum：已在重定位后重新计算；
* RSDP：已在 F-segment 找到并保存到 ``RsdpAddr``；
* RSDT/XSDT 表图：尚未在本叙事中展开；
* DSDT AML：尚未由 SeaBIOS 轻量解析；
* 平台定时器与周期 IRQ0：尚未完成最后初始化；
* TPM：尚未初始化；
* 存储、USB 与网络驱动：尚未探测介质；
* ``BootList``：尚无具体启动设备；
* GRUB：尚未被读取或执行；
* Linux：尚未装入内存。

成功找到 ``RsdpAddr`` 后，当前主线下一条调用是：

.. code-block:: c

   acpi_dsdt_parse();
   virtio_mmio_setup_acpi();
   return;

下一章先沿 RSDP 解释 RSDT/XSDT 怎样索引 FADT、MADT、MCFG 等表，再进入 FADT 指向的 DSDT，说明 SeaBIOS 为什么只解析 AML 的一个受限子集，而不是在固件里实现完整 ACPI Machine Language 解释器。

资料
----

* `SeaBIOS src/fw/romfile_loader.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/romfile_loader.c>`_；
* `SeaBIOS src/fw/paravirt.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/paravirt.c>`_；
* `SeaBIOS src/fw/biostables.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/biostables.c>`_；
* `SeaBIOS src/romfile.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/romfile.c>`_；
* `QEMU hw/acpi/bios-linker-loader.c <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/acpi/bios-linker-loader.c>`_；
* `QEMU include/hw/acpi/aml-build.h <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/include/hw/acpi/aml-build.h>`_；
* `QEMU hw/i386/acpi-build.c <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/acpi-build.c>`_；
* `ACPI Specification <https://uefi.org/specifications>`_。