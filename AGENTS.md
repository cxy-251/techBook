# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

当前只完成一篇开篇正文：

``LK-BOOT-001：设备上电后，x86-64 Linux 内核怎样被装入并完成解压？``

正文采用一条具体主线：

``x86-64 → SeaBIOS → GRUB → bzImage → Linux 6.12.95``。

范围从设备上电开始，到压缩内核完成解压并跳入解压后的 ``startup_64`` 为止。当前文件完成并经过阅读修改后，再决定下一篇内容。

## 内容依据

``aiBook`` 的 Linux Kernel Roadmap 用于确认用户希望掌握的知识范围。旧 Roadmap 把世界观、阅读方法、源码导航、内核 C 和构建系统放在启动链之前，真正的固件、bootloader 和内核解压直到 Part 5 才出现；``techBook`` 不沿用这个开篇顺序。

技术事实使用：

* Linux 6.12.95 的固定源码；
* Linux/x86 Boot Protocol；
* SeaBIOS 与 GRUB 在当前主线中的实际职责；
* 能够从源码文件、函数、CPU 模式、寄存器和内存布局确认的状态变化。

旧 ``aiBook/docs/LinuxK`` 只用于对比原内容在哪里绕远、重复或缺少关键细节。

## 正文写法

正文按时间顺序连续叙述，像追踪一次真实启动：

* 当前是谁在执行；
* CPU 处于什么模式；
* 代码和数据位于哪里；
* 这一段建立了什么状态；
* 下一次控制权跳转到哪个入口；
* 对应哪个源码文件、符号或协议字段。

概念在流程第一次需要时直接解释。章节不单独讲学习方法，也不在流程外铺设世界观、阅读指南或通用方法论。

## 接手顺序

开始工作前依次读取：

#. ``AGENTS.md``；
#. ``project/STATE.rst``；
#. ``docs/tracks/linux-kernel/index.rst``；
#. ``docs/tracks/linux-kernel/01-power-on-to-decompression.rst``；
#. ``manifests/tracks/linux-kernel.toml``；
#. ``main`` 最近的相关提交。

## 工作结束

完成正文或收到阅读反馈后，只更新当前正文、``project/STATE.rst`` 和 Linux 路径状态。