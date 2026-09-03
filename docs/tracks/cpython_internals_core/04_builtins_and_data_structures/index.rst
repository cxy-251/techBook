======================================================
第 4 模块：核心内建数据结构实现
======================================================

.. toctree::
   :maxdepth: 2
   :caption: 模块章节导航

   01_compact_dict_and_split_table
   02_unicode_flexible_representation
   03_pytuple_and_pylist_resizing
   04_set_and_frozenset_probing

模块概述
========

本模块解构 Python 高频内建容器与数据类型的底层 C 语言实现与内存优化。

剖析 Compact Dict（紧凑字典）设计、DKIX 稀疏哈希索引表与 Split-table 共享键表实现；拆解 Unicode 灵活字符串表示（Flexible String Representation, FSR）中的 1-byte (Latin-1), 2-byte (UCS-2), 4-byte (UCS-4) 内存压缩；解析元组不变性内存优化与列表过度分配（Over-allocation）扩容公式；详述 Set / Frozenset 开放寻址法与扰动哈希探查冲突解决算法。
