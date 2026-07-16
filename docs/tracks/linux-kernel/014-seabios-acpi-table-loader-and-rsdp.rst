第十四章：SeaBIOS 怎样执行 QEMU 的 ACPI table-loader 并搜索 RSDP？
================================================================

第十三章停在 ``smbios_setup()`` 返回之后。当前执行者仍是BSP上的SeaBIOS
``MainThread``；CPU处于32位保护模式，分页关闭、A20开启、IF=0，CMOS NMI屏蔽，
没有锁竞争或线程切换。PIR、MP与SMBIOS是已经结束的独立构造，本章不再修改它们。

下一段源码是：

.. code-block:: c

   if (CONFIG_FW_ROMFILE_LOAD) {
       int loader_err;

       loader_err = romfile_loader_execute("etc/table-loader");
       RsdpAddr = find_acpi_rsdp();
       if (RsdpAddr) {
           acpi_dsdt_parse();
           virtio_mmio_setup_acpi();
           return;
       }
       if (!loader_err)
           warn_internalerror();
   }
   acpi_setup();

固定SeaBIOS QEMU默认配置启用 ``CONFIG_FW_ROMFILE_LOAD``，所以BSP进入loader。本章只
走到 ``find_acpi_rsdp()`` 返回并把结果写入 ``RsdpAddr``；是否沿表图解析或走无RSDP
出口留给下一章。

QEMU为什么要交给固件做最后链接
------------------------------

QEMU在客户机CPU执行SeaBIOS之前已经根据q35设备、CPU topology与内存布局生成ACPI
内容。默认启用ACPI build时，fw_cfg至少发布三类对象：

::

   etc/acpi/tables   # FACS、DSDT、FADT、MADT、root tables等所在blob
   etc/acpi/rsdp     # RSDP blob
   etc/table-loader  # 固定格式链接命令流

QEMU构造blob时还不知道SeaBIOS最终能把它们放到哪些客户机物理地址。表内的FADT→DSDT、
RSDT/XSDT→子表、RSDP→root table等字段最初保存blob内offset，checksum字段也尚待最终
地址写入后计算。因此职责被分成两段：

::

   QEMU host side
   → 生成内容、offset和链接命令

   SeaBIOS guest side
   → 分配最终客户机地址
   → 把offset重定位成物理指针
   → 计算最终checksum

这是一种受限链接协议，不是SeaBIOS在客户机内重新执行QEMU的ACPI builder。

每条loader entry固定为128字节
-------------------------------

QEMU与SeaBIOS使用同一packed布局：4字节little-endian command，加124字节union/padding，
合计128字节。文件名字段固定56字节。SeaBIOS先调用 ``romfile_loadfile()`` 把整个
``etc/table-loader`` 读入临时内存；文件不存在便直接返回 ``-1``。

若总长度不是128的整数倍，函数告警、释放command blob并返回 ``-1``。长度合法时，它
用命令条数作为可能文件数的上界，为 ``romfile_loader_files`` 申请临时索引数组；
分配失败同样返回 ``-1``。只有这三类问题是loader的函数级失败：

::

   loader file missing
   command blob size malformed
   temporary files index allocation failed

建立索引后，BSP按原始顺序逐项解释command。QEMU把所有ALLOCATE entry插到命令流头部，
因此正常生成的指针和checksum命令不会先于对应文件分配。

ALLOCATE怎样把fw_cfg blob变成固件内存
--------------------------------------

``ROMFILE_LOADER_COMMAND_ALLOCATE`` 指定文件名、alignment和zone。SeaBIOS只接受：

::

   zone HIGH = 1
   zone FSEG = 2

非零alignment必须是2的幂；小于 ``MALLOC_MIN_ALIGN`` 的值会提升到最小分配对齐。
文件名最后一字节必须为0，防止越过56字节字段比较。QEMU正常命令为主ACPI blob请求
HIGH、64字节对齐，为RSDP请求FSEG、16字节对齐。

验证通过后，SeaBIOS用 ``romfile_find()`` 找对应fw_cfg文件。文件不存在或size为0时，
该命令直接返回，不增加 ``files->nfiles``；zone、alignment或名称无效则告警。找到文件
后， ``_malloc()`` 在目标zone申请与fw_cfg文件等长的连续区，再调用romfile ``copy``
填充。分配失败只发出 ``warn_noalloc()``；短复制会释放刚分配的区并告警。

只有分配与完整复制都成功时，SeaBIOS才把三元组加入临时索引：

::

   romfile descriptor
   final guest address
   file size

后续命令用文件名查这个索引，不直接相信QEMU提供的地址。

ADD_POINTER怎样完成重定位
-------------------------

``ROMFILE_LOADER_COMMAND_ADD_POINTER`` 同时查找destination与source。两者必须都已成功
ALLOCATE，目标offset加pointer size不能溢出或越过目标blob，size只能是1、2、4、8。

QEMU已经在目标字段中写入source blob内部offset。SeaBIOS执行：

::

   old little-endian value = source offset
   relocated value         = old value + source final guest base

然后把结果按相同宽度写回目标blob。例如FADT的DSDT字段最初只是
``etc/acpi/tables`` 内的DSDT offset；主blob落到HIGH后，这条命令才把它变成客户机可用
的物理地址。

代码检查目标范围与宽度，却没有单独检查相加结果能否装入小于8字节的字段；正常QEMU
builder会根据ACPI字段宽度和分配区选择满足协议的地址。畸形命令在这里不会得到事务
回滚。

ADD_CHECKSUM为什么必须在指针之后
---------------------------------

``ROMFILE_LOADER_COMMAND_ADD_CHECKSUM`` 指定同一blob中的checksum byte、range start与
range length。SeaBIOS验证checksum byte在文件内，范围加法不溢出且不越界，然后执行：

.. code-block:: c

   *checksum_byte -= checksum(range_start, range_length);

所有运算按8位截断，结果使指定范围的最终字节和为0。QEMU把checksum命令追加在相关
pointer patch之后，所以校验覆盖的是最终物理地址，而不是原始offset。

RSDP是最清楚的例子。QEMU要求它在FSEG按16字节对齐分配，先修补RSDT/XSDT地址，再为
前20字节写基本checksum；ACPI 2.0+还为36字节整体写extended checksum。

WRITE_POINTER为什么会修改宿主侧fw_cfg文件
-------------------------------------------

``ROMFILE_LOADER_COMMAND_WRITE_POINTER`` 与ADD_POINTER不同：destination可以是没有加载
到RAM的fw_cfg文件，source则必须在SeaBIOS内成功分配。BSP计算：

::

   pointer = source final guest base + source offset

它检查destination范围、source offset、1/2/4/8字节宽度以及pointer能否装入该宽度，
再经 ``qemu_cfg_write_file()`` 把little-endian pointer回写QEMU。

写回成功后，SeaBIOS尝试在high memory保存一项resume replay记录，包括pointer、fw_cfg
selector key、目标offset和宽度。之后固件恢复时 ``romfile_fw_cfg_resume()`` 可以重放
这些地址。若replay记录分配失败，当前回写已经发生，只是未来重放能力缺失；代码只
告警，不撤销写入。

为什么返回0不代表所有命令成功
------------------------------

四个命令handler都返回 ``void``。逐命令遇到文件缺失、内存不足、越界、非法宽度或短
复制时，只会告警、跳过该项，解释循环继续处理下一条。未知command更是按注释直接
跳过，不告警。

因此loader的真实错误模型是：

::

   function-level error
   → return -1
   → command stream not fully entered

   per-command error
   → warn or skip this command
   → continue
   → final return can still be 0

``romfile_loader_execute() == 0`` 只证明command blob格式可遍历且临时索引分配成功，
不证明每个blob都已分配、每个pointer都已修补或每个checksum都有效。它也不是原子
事务：前面已经成功分配和修补的对象不会因后面失败而回滚。

循环结束后，SeaBIOS释放临时files索引和command blob。成功ALLOCATE得到的HIGH/FSEG
区不能释放，因为ACPI表中的指针已经引用它们；WRITE_POINTER replay list也作为全局
状态保留。

RSDP搜索为什么不相信loader返回值
-------------------------------

无论 ``loader_err`` 是0还是 ``-1``，下一条源码都执行：

.. code-block:: c

   RsdpAddr = find_acpi_rsdp();

这使“命令流状态”和“最终是否存在可发现RSDP”成为两个正交结果。loader可能局部失败，
但RSDP相关命令已经完成；loader也可能函数级失败，而FSEG里此前已有有效RSDP。反过来，
loader返回0仍可能因为RSDP ALLOCATE或checksum命令软失败而搜索不到有效对象。

``find_acpi_rsdp()`` 不读取标准EBDA pointer另行跳转，也不遍历HIGH。它只在SeaBIOS的
``zonefseg_start`` 到 ``zonefseg_end`` 之间，从第一个16字节对齐地址开始，每16字节
检查一个候选。这与QEMU为 ``etc/acpi/rsdp`` 请求FSEG和16字节对齐相匹配。

候选RSDP怎样验证
----------------

``get_acpi_rsdp_length()`` 先检查8字节signature ``RSD PTR ``。基本部分固定20字节：

* 剩余FSEG范围必须至少容纳20字节；
* 前20字节8位checksum必须为0。

当revision大于1时，函数再读取RSDP自己的 ``length``：

* ``length`` 不能超过当前候选到FSEG末端的剩余范围；
* 整个扩展结构的8位checksum也必须为0。

任一条件失败就继续下一个16字节候选；全部失败才返回 ``NULL``。函数在这里不验证
RSDT/XSDT地址、root signature或任何子表，它只证明FSEG中有一份边界与checksum合格
的RSDP。

本章为什么不能以“RSDP成功”作为唯一结束状态
-------------------------------------------

固定q35默认ACPI build的正常路径会让QEMU提供tables、RSDP与loader，SeaBIOS完成链接后
找到RSDP。但稳定叙事还必须保留源码真实失败边界，因为当前函数没有把逐命令失败汇总
到 ``loader_err``。

所以本章在赋值后结束，状态按结果分叉：

::

   found
   → RsdpAddr points into FSEG
   → next branch parses DSDT and probes ACPI-described virtio-mmio

   not found
   → RsdpAddr = NULL
   → loader_err == 0: warn_internalerror()
   → then acpi_setup()

   not found + loader_err == -1
   → no extra loader-success warning
   → then acpi_setup()

注意：即使 ``loader_err == -1``，只要搜索找到有效RSDP，源码仍优先进入found分支；
``loader_err`` 不会否决已经可验证的RSDP。

本章结束状态
------------

* current executor：BSP上的SeaBIOS ``MainThread``；
* CPU/mode：32位保护模式，分页关闭，A20开启，IF=0，CMOS NMI屏蔽；
* table-loader input：已尝试读取并按128字节entry遍历；
* final ACPI allocations：成功项保留在HIGH或FSEG，失败项无全局回滚；
* temporary command blob/files index：已释放；
* WRITE_POINTER replay entries：仅为成功回写且成功登记的项保留；
* ``loader_err``：只区分函数级0/ ``-1``，不汇总逐命令错误；
* ``RsdpAddr``：正常q35默认路径指向FSEG有效RSDP；失败路径为 ``NULL``；
* RSDP validation：signature、范围、基本checksum及条件extended checksum已检查；
* RSDT/XSDT/FADT/DSDT：尚未由SeaBIOS当前控制流遍历；
* next entry： ``if (RsdpAddr)``。

关键边界
--------

#. QEMU生成表内容与offset，SeaBIOS决定最终客户机地址并完成重定位。
#. loader entry固定128字节，文件名固定56字节，数值字段按little endian解释。
#. QEMU把ALLOCATE放在引用命令之前；SeaBIOS仍逐项验证实际分配结果。
#. ADD_POINTER把目标字段已有source offset加上source最终基址。
#. ADD_CHECKSUM作用于pointer patch之后的最终字节。
#. WRITE_POINTER修改fw_cfg宿主文件；replay登记失败不会撤销已经完成的写回。
#. 逐命令错误不传播到 ``romfile_loader_execute()`` 返回值，返回0不是全成功承诺。
#. loader不是事务；后续失败不会回滚先前成功的分配或patch。
#. ``find_acpi_rsdp()`` 无条件运行，结果不能由 ``loader_err`` 推导。
#. RSDP搜索只扫SeaBIOS FSEG并按16字节对齐，不在本章验证root或子表。
#. 正常q35命中RSDP，但源码失败出口仍必须保留，供状态与回滚边界闭合。

下一入口
--------

下一章从：

.. code-block:: c

   if (RsdpAddr) {
       acpi_dsdt_parse();
       virtio_mmio_setup_acpi();
       return;
   }

开始。found分支将沿RSDP优先查XSDT、回退RSDT，再通过FADT的32位DSDT字段进入受限
AML解析；not-found分支则区分告警条件并进入当前已经退化的 ``acpi_setup()``。

资料
----

* `SeaBIOS固定提交：table-loader命令格式 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/romfile_loader.h#L1-L89>`_
* `SeaBIOS固定提交：table-loader执行与错误模型 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/romfile_loader.c#L1-L265>`_
* `SeaBIOS固定提交：RSDP长度、checksum与FSEG搜索 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/biostables.c#L89-L134>`_
* `SeaBIOS固定提交：QEMU平台loader、搜索与分支顺序 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/paravirt.c#L301-L324>`_
* `QEMU固定提交：BIOS linker/loader协议与ALLOCATE前置 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/acpi/bios-linker-loader.c#L1-L300>`_
* `QEMU固定提交：RSDP的FSEG分配、pointer与checksum命令 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/acpi/aml-build.c#L1821-L1899>`_
* `QEMU固定提交：PC ACPI blob与loader文件发布 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/acpi-build.c#L2278-L2344>`_
