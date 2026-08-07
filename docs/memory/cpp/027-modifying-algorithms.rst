第027章：Modifying Algorithms
==============================

核心知识点
----------

* 修改类 algorithm 通过 iterator 覆盖、搬运、替换、压缩或重排已有元素；容器结构变化仍由容器成员或 insert iterator 承担。
* ``copy`` / ``move`` / ``transform`` 都需要合法输出位置。普通目标 iterator 要求已有可赋值对象；``back_inserter`` 等适配器把写入转换为插入。
* ``copy_if`` 的输出数量由谓词决定，使用 inserter 能把不确定输出长度交给目标容器增长路径。
* range ``std::move`` 逐个执行移动赋值/构造语义；源对象生命周期仍存在，只进入各类型规定的 moved-from 状态。
* ``fill`` / ``generate`` 覆盖已有对象，不会凭空增加容器 ``size``。
* ``remove`` / ``remove_if`` 的语义是稳定压缩保留元素并返回新的逻辑末尾；容器长度不变，典型用法是 erase-remove。
* ``reverse``、``rotate``、``shuffle`` 改变元素顺序但通常保持元素数量；引用和 iterator 是否继续表示同一业务元素要结合算法移动与容器规则判断。
* 输入输出重叠时要检查方向：向右覆盖重叠区域通常使用 ``copy_backward`` / ``move_backward``；向左压缩适合正向路径。
* 修改 algorithm 通常不是事务操作；元素赋值、移动、比较或用户操作抛异常后，区间可能已经被部分修改。

关键路径
--------

1. 确定输入范围和实际写入范围，先判断目标位置是覆盖已有对象还是通过 inserter 创建新对象。
2. 对 ``copy`` / ``move`` / ``transform`` 检查目标容量与输入输出重叠关系。
3. 对 ``fill`` / ``generate`` 确认区间内对象已经存在；需要创建元素时转入容器构造、``resize``、``insert`` 或 inserter 路径。
4. 对 ``remove_if`` 追踪“读取位置 → 写入位置 → logical_end”，之后再由 ``erase(logical_end, end())`` 结束尾部对象生命周期。
5. 对 ``reverse`` / ``rotate`` / ``shuffle`` 追踪元素相对位置变化，并判断外部保存的位置对象是否仍满足业务假设。
6. 最后检查元素移动/赋值是否可能抛异常，以及算法中止时哪些前缀已经完成写入。

概念辨析
--------

* **copy 与插入**：``copy`` 只向输出 iterator 赋值；是否插入由 output iterator 本身决定。
* **std::move(obj) 与 std::move(first,last,out)**：前者是值类别转换工具，后者是逐元素移动的 range algorithm。
* **remove 与 erase**：``remove`` 重排值并返回逻辑尾；``erase`` 才缩短容器并销毁元素。
* **fill 与 resize**：``fill`` 覆盖已有元素，``resize`` 改变有效元素数量。
* **reverse 与 sort**：``reverse`` 只翻转当前顺序，不建立比较器定义的全局有序关系。
* **重叠范围与方向**：正向复制、后向复制的选择取决于尚未读取的源数据是否会被提前覆盖。

本章结论
--------

修改 algorithm 的核心检查顺序是“写入形态 → iterator 能力 → 目标空间 → 重叠方向 → 返回位置 → 容器失效与异常边界”。尤其要记住：算法可以重排和值写入，容器的 ``size``、节点和对象生命周期通常仍需由容器接口完成。