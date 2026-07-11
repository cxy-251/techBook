阅读契约
========

目标
----

这本书使用最小实验验证 Linux 内核源码路径。每章只解释实验实际经过的函数、数据结构和状态变化。

Source contract
---------------

开始源码级章节前，必须在 ``sources.lock`` 与书籍 manifest 中固定：

* upstream repository；
* release 或 tag；
* exact commit；
* architecture；
* kernel config；
* compiler/toolchain；
* runtime environment。

实验规则
--------

* 用户态程序、内核配置、执行脚本和输出保存在 ``labs/linux-kernel/``。
* 命令必须可以复制执行。
* 输出必须来自真实运行或明确的采集步骤。
* 每章至少包含一个边界或失败用例。
* 当前环境无法验证时，manifest 标记为 ``evidence-pending``。

源码路径规则
------------

调用路径只保留解释当前现象所需节点。每个节点记录文件、符号、关键输入、判断和传出的状态。无关分支放入候选问题池。

写作规则
--------

正文按“问题 → 实验 → 输出 → 观察 → 最短源码路径 → 解释 → 失败边界 → 检查题”推进。问题解决后结束，不增加重复总结。
