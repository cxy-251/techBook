第065章：listobject.c and unicodeobject.c
=========================================

核心知识点
----------

* CPython ``list`` 是动态 ``PyObject *`` 指针数组。逻辑长度与底层容量分离，元素对象本体不存放在 list 内部，list 只保存并管理元素引用。
* ``PyListObject`` 的核心关系是 ``Py_SIZE`` 表示长度，``ob_item`` 指向元素指针数组，``allocated`` 表示容量。随机索引主要是边界检查 + 指针下标访问。
* ``append`` 在容量足够时只需尾部写指针并调整引用；容量不足时进入 ``list_resize``。over-allocation 让连续 append 获得摊还 O(1)。
* ``insert(0, x)``、``pop(0)`` 和中间插删需要移动一段元素指针；list 是动态数组，不适合把“头部插删”理解成链表操作。
* list slicing 会创建新 list 并复制元素引用，属于浅拷贝；元素对象继续共享。切片成本与切片长度相关。
* list 销毁要区分三层：list object header、元素指针数组、元素对象引用。减少元素引用可能触发元素自身析构和任意 Python 代码。
* CPython ``str`` 是不可变 Unicode 对象，使用 flexible string representation。内部 ``kind`` 根据最大 code point 选择 1、2 或 4 字节宽度，而不是固定 UTF-8 存储。
* ASCII 字符串是最高频快路径：compact ASCII 可以用更小 header，并让 canonical data 与 UTF-8 单字节表示天然一致。
* 非 ASCII compact string 仍可把 header 与字符数据放在一次连续分配中；字符范围越宽，``kind`` 越宽，内存成本越高。
* ``len(str)`` 统计 Python 字符/code point 数量，不等于 UTF-8 bytes 长度，也不等于内部数据占用字节数。
* ``str`` 不可变，因此 hash 可以缓存，字符数据可以安全共享，字符串可作为 dict key。拼接、替换、切片通常创建新字符串。
* interning 让高频标识符类字符串复用 canonical object，减少相等性比较和重复内存；interning 不是所有相等字符串都自动 ``is`` 相同的语言保证。

关键路径
--------

list append：

::

    list.append(obj)
       ↓
    size < allocated ?
       ├─ yes → INCREF/steal as required → ob_item[size] = obj → size++
       └─ no
            ↓
         list_resize(newsize)
            ↓
         allocate/reallocate pointer array
            ↓
         preserve existing PyObject* pointers
            ↓
         append new pointer

list 头部插入：

::

    insert(0, obj)
       ↓
    ensure capacity
       ↓
    move existing pointers right
       ↓
    write new pointer
       ↓
    update size

slice：

::

    src[a:b]
       ↓
    allocate new list
       ↓
    copy PyObject* references
       ↓
    INCREF copied elements
       ↓
    new list; element identity preserved

Unicode 创建与访问：

::

    Python str value
       ↓
    determine length + maximum code point
       ↓
    choose kind: 1 / 2 / 4 byte
       ↓
    choose compact ASCII / compact non-ASCII / other form
       ↓
    canonical data
       ↓
    index/read/hash/string algorithms

字符串 hash：

::

    hash(s)
      ↓
    cached hash exists?
      ├─ yes → reuse
      └─ no  → compute from immutable content → cache

概念辨析
--------

* list 连续的是“元素指针”，不是所有元素对象的实际内存。
* list 的 ``size`` 与 ``allocated`` 不同；``sys.getsizeof`` 的阶梯增长来自容量，不代表元素对象大小。
* ``append`` 摊还 O(1) 不等于每次都 O(1)；resize 那一次需要重新分配/搬运指针。
* list slice 是浅拷贝，不是元素深拷贝。
* ``str`` 内部 kind 不是 UTF-8/UTF-16 这种外部编码选择；它是 CPython 的 canonical code point 存储宽度。
* Python 字符串长度、UTF-8 字节长度和对象内存大小是三个不同量。
* compact string 描述内存布局，interning 描述对象复用策略，hash cache 描述派生值缓存，三者不能混为一类优化。
* 相等字符串可以是不同对象；业务逻辑只能依赖 ``==``，不能依赖 interning 导致的 ``is``。

本章结论
--------

``listobject.c`` 的核心是“可增长的对象指针数组”，性能由容量、指针移动和新 list 创建决定；``unicodeobject.c`` 的核心是“不可变 code point 序列 + 自适应字符宽度 + compact layout”。理解这两个文件后，list 的 append/insert/slice 成本和 str 的长度、编码、hash、interning、内存占用都能从对象布局直接推导。