第015章：String
===============

核心知识点
----------

``std::string`` 是 ``std::basic_string<char>`` 的别名。``basic_string`` 的三个关键模板参数是字符类型 ``CharT``、字符操作策略 ``Traits`` 和动态存储策略 ``Allocator``。

string 管理的是 ``CharT`` 序列，不自动理解 Unicode 字符、字形或语言学边界。``std::string`` 通常保存字节或 UTF-8 code unit；``u16string``、``u32string`` 也只是不同宽度 code unit 序列。

现代 ``basic_string`` 保证有效字符位于连续范围 ``[data(), data()+size())``。``data()[size()]`` 处由 string 维护一个值为 ``CharT()`` 的终止位置，用于 ``c_str()`` 与 C 字符串接口；这个终止字符不计入 ``size()``。

``size()`` 是有效字符数量，``capacity()`` 是无需重新分配即可容纳的有效字符上限。``append``、``push_back``、``insert``、某些 ``replace`` 和 ``reserve`` 等操作可能改变内部缓冲区，从而使旧 pointer、reference、iterator 和基于旧缓冲区的 ``string_view`` 悬空。

``find`` 返回下标，失败时返回 ``npos``；``substr`` 创建新的拥有型 string，因此通常涉及复制并可能分配。只需要只读切片时，``string_view`` 可以避免复制，但它不拥有字符数据，生命周期依赖原 string。

``char_traits`` 统一提供字符比较、长度、查找、copy/move 等底层操作；allocator 只改变动态字符缓冲区来源，不改变 string 的连续存储、长度和查找语义。

C 接口有两种边界模型：零终止与显式长度。含内嵌 ``'\0'`` 的 string 仍可有更大的 ``size()``，而 ``strlen(c_str())`` 会在第一个零字符处停止。

关键路径
--------

尾部追加路径：

``计算新 size → 检查 capacity → 容量足够则原地写入尾部 → 更新 size 和终止字符；容量不足则 allocate 新缓冲 → 复制/移动旧字符 → 写入新增字符 → 更新终止位置 → 释放旧缓冲``。

中间 ``insert``：

``定位 pos → 确保容量 → 后缀向后移动 → 写入新字符区间 → 更新 size → 写入新的 null terminator``。

``erase``：

``确定删除区间 → 后缀向前移动覆盖空洞 → 缩短 size → 把 data()[size()] 恢复为终止字符``。

``find``：

``从指定位置扫描字符序列 → 通过 Traits 比较 → 命中返回 index → 未命中返回 npos``。

``substr``：

``验证 pos/count → 取源字符串子范围 → 构造一个新的 basic_string → 新对象拥有独立字符存储``。

``string_view`` 借用路径：

``string 拥有 data/size → view 保存指针+长度 → 原 string 若销毁或重分配 → view 立即失效``。

概念辨析
--------

``std::string`` 不等于 C 字符串。string 自己记录长度，可以包含内嵌零字符；C 字符串通常以首个 ``'\0'`` 作为结束边界。

``data()`` 连续不等于地址稳定。任何可能重新分配的修改后，都应重新取得 data、iterator 和 string_view。

``substr`` 不等于零拷贝视图。substr 返回拥有型 string；``string_view::substr`` 才是对已有字符范围的非拥有切片。

``string_view`` 不等于安全 string 引用。它只保存地址和长度，不延长原字符缓冲区生命周期。

``reserve`` 不等于改变字符串长度。它改变容量策略；真正的字符数量仍由 size 决定。

``char`` 不等于“一个 Unicode 字符”。UTF-8 中一个用户可见字符可能占多个 char code unit；按 ``operator[]`` 访问的是 code unit。

本章结论
--------

分析 string 时固定按“谁拥有字符数据 → 当前 size/capacity → 操作是否可能重分配 → 旧位置对象是否失效 → 接口使用零终止还是显式长度 → 是否需要拥有型 substring 或借用型 string_view”判断。string 的核心不是文本语义，而是连续字符序列、所有权和容量管理。