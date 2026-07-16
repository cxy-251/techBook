项目状态
========

最后更新
--------

2026-07-16。

当前模式
--------

::

   mode                 = retrospective-audit
   forward production   = paused
   content present      = 001-193
   audit verified       = 001-018
   verified_through     = 018
   blocked batches      = none
   next batch           = 019-021
   next batch status    = ready

历史正文已经写到第193章，但只有001—018按
``project/LINUX_KERNEL_CONTRACT.rst`` 完成固定源码审查。019—193仍是 ``pending``，
不得把“文件存在”写成“技术内容已验证”。第193章之后的新生产保持暂停。

最近完成批次
------------

`016—018审查报告 <audits/linux-kernel/016-018.rst>`_：状态 ``repaired``。

本批修复了：

* 第016章证明固定q35到 ``timer_setup()`` 时只会保留KVM TSC或ICH9 PM timer，不会再走
  PIT校准TSC/PIT fallback；
* 第016章补齐 ``rtc_updating()`` 超时返回被忽略、IRQ发布不等于handler已执行、IRQ8
  可路由不等于PIE开启；
* 第016章纠正默认TPM已启动并测量的错误：固定QEMU无TPM2/TCPA表， ``tpm_setup()``
  直接返回；
* 第017章把standard VGA正常路径与graphics override、ROM失败、INT 10h未接管分支拆开；
* 第017章证明固定无TPM时Option ROM measurement是no-op，mode 3调用也没有成功校验；
* 第017章补齐16位IF=1调用帧、 ``finish_preempt()`` 的单次yield与MainThread IF=0边界；
* 第018章纠正q35默认必有EHCI/UHCI的错误：固定MachineState USB默认false，四类扫描全空；
* 第018章把ICH9 EHCI/UHCI完整枚举降为显式 ``usb=on`` 条件分支；
* 第018章固定QEMU i8042与 ``PNP0303/_STA=0x0f`` 的确定命中，并区分IRQ12路由与mouse
  仍disabled。

第018章已验证结束状态
---------------------

::

   current executor       = SeaBIOS device_hardware_setup() on BSP/MainThread
   completed calls        = usb_setup(), ps2port_setup()
   next call              = block_setup()
   current CPU            = BSP
   CPU mode               = 32-bit protected mode
   paging                 = disabled
   A20                    = enabled
   NMI                    = masked by CMOS index bit 7
   maskable interrupts    = IF=0
   PIC additionally open  = IRQ0, IRQ1, IRQ8, IRQ12; old IRQ2/IRQ13 remain open
   internal timer         = KVM-provided scaled TSC or ICH9 PM timer
   PIT/BDA clock          = PIT channel0 mode2/count65536; BDA timer_counter initialized
   RTC periodic           = IRQ8 vector/routing ready; RTCusers=0 and PIE off
   fixed TPM              = absent; no TPM2/TCPA table, event log or PCR measurement
   ThreadControl          = 1; threads_during_optionroms=false
   display default        = standard VGA when graphics is not disabled/overridden
   VGA result             = mode3 requested; failure is nonfatal and not returned to maininit
   sercon                 = absent without etc/sercon-port
   fixed machine USB      = false; no EHCI/UHCI controller or USB worker/object
   fixed i8042            = present; PNP0303 _STA=0x0f
   PS/2 IRQ routes        = IRQ1->INT09h and IRQ12->INT74h installed/unmasked
   PS/2 keyboard worker   = may still be running; success/failure is nonfatal
   present vCPU count     = not fixed by current -smp conditions
   no -smp override       = present=1; no AP executed entry_smp
   explicit multi-vCPU    = APs normally replay logged prefix and halt with IF=0
   fixed AHCI             = PCI function/BAR exist; SeaBIOS block driver not entered
   BootList               = no USB entry; final set not formed
   ordinary option ROMs   = not scanned
   GRUB/Linux             = not loaded

下一入口
--------

第019章从 ``device_hardware_setup()`` 的下一条调用继续：

::

   usb_setup() returns with no fixed USB controllers
   → ps2port_setup() publishes IRQ1/12 and starts PS/2 worker
   → block_setup()
   → fixed q35 ICH9 AHCI SATA port 0 path

019—021批次必须先读取：

#. ``AGENTS.md``；
#. ``project/LINUX_KERNEL_CONTRACT.rst``；
#. 本文件；
#. ``project/audits/linux-kernel/index.rst``；
#. ``project/audits/linux-kernel/016-018.rst`` 的“整批控制流与交接”、
   “执行上下文与对象账本”、“发现并修复”中的第018章与“连续性检查”；
#. 第018章末尾、第019—021章正文和第022章开头；
#. ``.sources/seabios`` 与 ``.sources/qemu`` 固定提交中 ``block_setup``、AHCI、
   drive/boot registration、worker等待及相邻调用涉及的源码。

不要读取001—017全文、完整193章目录或历史前向检查点，除非审查中发现必须回溯的矛盾。

源码缓存
--------

::

   .sources/seabios HEAD = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   .sources/qemu HEAD    = a759542a2c62f0fd3b65f5a66ad9868201014669

两个缓存均由 ``.gitignore`` 排除。QEMU使用稀疏检出；缺少目录时按当前批次补齐。

已知结构债务
------------

* 第065章存在两个正文文件；
* 第066章存在两个正文文件；
* 001—073尚未逐章登记到当前track manifest；
* 019—193尚未按专用合同补齐章末结构和精确证据，必须随顺序审查处理，不能批量机械改写。

历史前向终点
------------

回溯审查开始前的第193章终点保存在
``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst``。它只用于审查闭合后的对照，不是当前
执行依据，也不代表UDP入口已经验证。
