========================================================================================
01.03 outtmpl 输出模板引擎与动态格式化安全解析
========================================================================================

.. note:: 前置背景与上下文承接
   在上一节中，我们深入剖析了 ``YoutubeDL`` 的调度中枢与多态实体流转管线。当视频实体图谱在 ``process_video_result`` 中完成清洗与选流决议后，多媒体数据即将走向物理落盘。然而，在分布式网络抓取与批量归档场景中，如何依据异构多媒体元数据（如频道名、发布日期、章节、分辨率、视频格式、多语言字幕）动态生成合法、安全、可预测的文件系统路径，是下载引擎面临的核心难题。本节将深入剖析 ``yt-dlp`` 输出模板解析引擎（Outtmpl），揭示其如何通过双层正则表达式解析、AST 字段树遍历、即时算术求值器、格式化修饰符矩阵以及沙箱命令注入防御机制，构建起高韧性的路径生成中枢。

***
Outtmpl 双层正则表达式解析模型
***

在 ``yt-dlp`` 中，输出模板（如 ``%(uploader)s/%(upload_date>%Y-%m-%d)s - %(title)s [%(id)s].%(ext)s``）并不是简单的 Python 原生字符串插值（``%`` 运算符或 ``str.format``），而是一套具备词法分词、嵌套解构与表达式求值能力的专用微型领域特定语言（DSL）。

``YoutubeDL.prepare_outtmpl()`` 采用了巧妙的 **双层正则表达式状态机** 模型：

.. code-block:: text
   :caption: Outtmpl 双层正则解析与求值流向图

   用户输入的原始模板 outtmpl
               |
               v
   +-------------------------------------------------------------------+
   | 1. 外层正则分词 (EXTERNAL_FORMAT_RE)                              |
   |    - 扫描捕获: prefix, has_key, key, conversion, min_width, fmt  |
   +-----------------------------------+-------------------------------+
                                       | 提取关键表达式 key 与格式 fmt
                                       v
   +-------------------------------------------------------------------+
   | 2. 内层语法树解构 (INTERNAL_FORMAT_RE)                            |
   |    - 解构语法块: negate, fields, maths, strf_format,              |
   |      alternate (,), replacement (&), default (|)                  |
   +-----------------------------------+-------------------------------+
                                       |
                                       v
   +-------------------------------------------------------------------+
   | 3. AST 字段树遍历与动态求值 (get_value)                           |
   |    - _traverse_infodict(fields) 提取多层嵌套属性                  |
   |    - 动态算术求值 (MATH_FUNCTIONS: +, -, *)                       |
   |    - 日期宏格式化 (strftime_or_none)                              |
   |    - 备选字段降级 (alternate) 与默认值兜底 (default)              |
   +-----------------------------------+-------------------------------+
                                       |
                                       v
   +-------------------------------------------------------------------+
   | 4. 格式修饰符转换与占位符替换 (create_key)                        |
   |    - 修饰符编码: l(列表), j(JSON), h(HTML), q(Shell引用),         |
   |      U(Unicode归一化), D(十进制单位), S(文件名清洗)               |
   |    - 注入临时隔离字典 TMPL_DICT[key\0format] = value              |
   +-----------------------------------+-------------------------------+
                                       |
                                       v
   最终输出可供 Python 安全插值的规整模板与临时参数字典

外层正则与隔离键编码机制
~~~~~~~~~~~~~~~~~~~~~~~~

外层分词正则 ``EXTERNAL_FORMAT_RE`` 继承自标准 printf 语法规范并进行了扩展：

.. code-block:: python

   STR_FORMAT_RE_TMPL = r'''(?x)
       (?<!%)(?P<prefix>(?:%%)*)
       %
       (?P<has_key>\((?P<key>{0})\))?
       (?P<format>
           (?P<conversion>[#0\-+ ]+)?
           (?P<min_width>\d+)?
           (?P<precision>\.\d+)?
           (?P<len_mod>[hlL])?
           {1}
       )
   '''

为了避免模板字符串内部包含的特殊字符（如 ``%``、括号、转义符）与 Python 内置 ``%`` 格式化发生歧义碰撞，引擎设计了 **空字符隔离编码（Null-byte Key Encoding）**：

.. code-block:: python

   # 将内部 key 与格式类型拼接为带空字符 \0 的唯一键名
   key = '{}\0{}'.format(key.replace('%', '%\0'), outer_mobj.group('format'))
   TMPL_DICT[key] = value
   return '{prefix}%({key}){fmt}'.format(key=key, fmt=fmt, prefix=outer_mobj.group('prefix'))

通过在字典键名中嵌入 ``\0``，引擎将复杂的 DSL 表达式转换为 Python 原生字典无法意外匹配的绝对唯一键，实现了沙箱化的字符串安全求值。

---
AST 字段树遍历与动态算术求值器
---

``INTERNAL_FORMAT_RE`` 负责将括号内部的微语法解构为语法树节点：

.. code-block:: python

   INTERNAL_FORMAT_RE = re.compile(rf'''(?xs)
       (?P<negate>-)?
       (?P<fields>{FIELD_RE})
       (?P<maths>(?:{MATH_OPERATORS_RE}{MATH_FIELD_RE})*)\
       (?:>(?P<strf_format>.+?))?
       (?P<remaining>
           (?P<alternate>(?<!\),[^|&)]+)?
           (?:&(?P<replacement>.*?))?
           (?:\|(?P<default>.*?))?
       )$''')

嵌套字典与切片提取算法 (`_traverse_infodict`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

多媒体元数据通常具有深度嵌套层次（例如 ``formats.0.http_headers.User-Agent`` 或 ``subtitles.en.-1.url``）。``_traverse_infodict`` 实现了支持对象层级、数组切片与多键映射的遍历器：

.. code-block:: python

   def _traverse_infodict(fields):
       fields = [f for x in re.split(r'\.({.+?})\.?', fields)
                 for f in ([x] if x.startswith('{') else x.split('.'))]
       for i, f in enumerate(fields):
           if not f.startswith('{'):
               fields[i] = _from_user_input(f)
               continue
           # 支持字典映射语法，如 {id,title}
           fields[i] = {k: list(map(_from_user_input, k.split('.'))) for k in f[1:-1].split(',')}
       return traverse_obj(info_dict, fields, traverse_string=True)

* **点号路径导航**：``uploader.0.name`` 自动依次执行字典查找与列表索引；
* **切片范围支持**：``thumbnails.0:3.url`` 提取前三个封面的 URL 列表；
* **负向索引**：``formats.-1.format_id`` 快速提取最优或末尾格式。

即时动态算术求值引擎
~~~~~~~~~~~~~~~~~~~~

在时间戳偏移、章节时长或文件大小计算中，模板允许直接嵌入算术运算（如 ``%(duration+60)s`` 或 ``%(playlist_index*2-1)02d``）：

.. code-block:: python

   MATH_FUNCTIONS = {
       '+': float.__add__,
       '-': float.__sub__,
       '*': float.__mul__,
   }

求值器通过线性扫描 ``offset_key``，支持 **常量与动态字段混合运算**。若运算数为字段名（例如 ``%(view_count-like_count)d``），引擎会递归调用 ``_traverse_infodict`` 提取相应字段值并强转为浮点数参与运算；遇到除零或类型异常时自动返回 ``None`` 并触发备选分支。

---
条件分支、替换语法与修饰符矩阵
---

为了在元数据缺失或不完整时生成高可读性路径，``yt-dlp`` 提供了完备的条件回退与替换语法：

.. list-table:: 模板高级控制语法与语义
   :widths: 24 36 40
   :header-rows: 1

   * - 语法结构
     - 表达式范例
     - 行为语义与解析逻辑
   * - 备选字段级联 (``,``)
     - ``%(track,title)s``
     - 优先使用 ``track``，若为 ``None`` 则自动回退到 ``title``
   * - 替换模板修饰 (``&``)
     - ``%(series&Season {0}|No Series)s``
     - 当字段存在时将其代入 ``{0}`` 格式化，否则输出默认值
   * - 默认值兜底 (``|``)
     - ``%(artist|Unknown Artist)s``
     - 当字段缺失或为 ``None`` 时输出指定的字面量默认值
   * - 日期时间宏 (``>``)
     - ``%(timestamp>%Y/%m/%d %H:%M)s``
     - 将 UNIX 时间戳或 ISO 日期字符串格式化为指定日期掩码

格式修饰符矩阵 (Type Modifiers)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在标准 Python 转换字符（``s, d, f, x, r``）之外，引擎扩展了多种针对媒体元数据的专用修饰符：

.. list-table:: Outtmpl 扩展格式修饰符对照表
   :widths: 14 18 32 36
   :header-rows: 1

   * - 修饰符
     - 转换类型
     - 核心转换逻辑与标志位 (Flags)
     - 典型输出示例
   * - ``l``
     - 列表展开 (List)
     - ``', '.join()``；若声明 ``#`` 标志则改用换行符 ``'
'`` 连接
     - ``%(tags)l`` -> ``rock, pop, indie``
   * - ``j``
     - JSON 序列化
     - 输出 JSON 字符串；声明 ``#`` 缩进 4 格，声明 ``+`` 保持非 ASCII
     - ``%(categories)#+j``
   * - ``h``
     - HTML 转义
     - 执行 ``escapeHTML()`` 消除特殊字符
     - ``%(title)h`` -> ``Tom &amp; Jerry``
   * - ``q``
     - Shell 安全引用
     - 调用 ``shell_quote()`` 进行平台安全的引号包裹
     - ``%(title)q`` -> ``"My Video's Title"``
   * - ``B``
     - 二进制字节流
     - 执行底层 UTF-8 编码与字节级截断格式化
     - ``%(id)B``
   * - ``U``
     - Unicode 归一化
     - 执行 ``unicodedata.normalize``；支持 ``#`` (NFD) 与 ``+`` (NFKC)
     - ``%(title)#+U``
   * - ``D``
     - 十进制/二进制后缀
     - 自动添加 ``K, M, G, T`` 单位；声明 ``#`` 时按 ``1024`` 进制换算
     - ``%(filesize)#D`` -> ``12.5MiB``
   * - ``S``
     - 文件名安全清洗
     - 对字段调用 ``sanitize_filename()``，支持 ``#`` 严格 ASCII 模式
     - ``%(title)#S``

---
沙箱安全防御：防范命令注入漏洞 (GHSA-69qj-pvh9-c5wg)
---

在 ``yt-dlp`` 中，模板解析引擎不仅用于生成物理落盘路径，还用于在 ``--exec`` 参数中向系统 Shell 传递命令（如 ``--exec "ffmpeg -i %(filepath)q output.mp4"``）。

在过去的安全演进中，恶意视频标题可能包含反引号、分号或管道符（例如 ``Title$(rm -rf /)``）。如果模板引擎直接将其替换为未经转义的 ``%()s``，将引发严重的远程命令注入漏洞。

.. code-block:: text
   :caption: --exec 沙箱安全防御决策矩阵

                         --exec 命令模板输入
                                 |
                                 v
   +-------------------------------------------------------------------+
   | 1. prepare_outtmpl(outtmpl, info_dict, _exec=True)                |
   +-----------------------------------+-------------------------------+
                                       |
                                       v
   +-------------------------------------------------------------------+
   | 2. 转换类型合法性强校验: fmt[-1] in SAFE_EXEC_CONVERSIONS ('difq') |
   |    - 严禁在 --exec 中使用 %()s 或 %()r                            |
   |    - 必须强制声明为 %()q (Shell Quote) 或数值型 %()d               |
   +-----------------------------------+-------------------------------+
                                       |
                        +--------------+--------------+
                        |                             |
                     不合规                        合规
                        v                             v
   [抛出 UnsafeExecExpansionError]     +-------------------------------+
   [拒绝执行外部命令并中断进程]         | 3. 默认值与 NA 字符安全性检测 |
                                       |    检测 UNSAFE_DEFAULT_CHARS  |
                                       |    ('"\' 
	;&|^$%*<>{}[]`#\)|
                                       +---------------+---------------+
                                                       |
                                                       v
                                       [安全生成经转义的 Shell 执行命令]

核心安全约束规范
~~~~~~~~~~~~~~~~

1. **转换类型白名单限制**：
   在 ``_exec=True`` 模式下，格式字符仅允许 ``'d', 'i', 'f', 'q'``。任何尝试使用 ``%(title)s`` 的行为都会直接被 ``UnsafeExecExpansionError`` 拦截，强制开发者与用户采用安全引用宏 ``%(title)q``。
2. **默认值字符集审查**：
   ``UNSAFE_DEFAULT_CHARS`` 严密监控在默认值分支中注入恶意 Shell 元字符（如 ``;``, ``|``, ``&``, `````）。即便主字段为空，攻击者也无法通过 ``%(missing_field|; evil_cmd)q`` 突破沙箱。

---
文件名清洗与跨平台兼容性 (sanitize_filename)
---

物理落盘时，不同操作系统对文件名字符集与长度有着严格限制（如 Windows 严禁 ``: * ? " < > | / \``，并保留 ``CON, PRN, AUX, NUL`` 等设备名）。

``yt-dlp/utils/_utils.py`` 中的 ``sanitize_filename()`` 构建了确定性的清洗流水线：

.. code-block:: python

   def sanitize_filename(s, restricted=False, is_id=NO_DEFAULT):
       if s == '':
           return ''
       def replace_insane(char):
           if restricted and char in ACCENT_CHARS:
               return ACCENT_CHARS[char]  # 重音字符转写 (如 é -> e)
           elif is_id is NO_DEFAULT and not restricted and char in '"*:<>?|/\':
               # Windows 非法字符映射为全角 Unicode 等价字形
               return {'/': '\u29F8', '\': '\u29f9'}.get(char, chr(ord(char) + 0xfee0))
           elif char == '?' or ord(char) < 32 or ord(char) == 127:
               return ''
           elif char == ':':
               return '\0_\0-' if restricted else '\0 \0-'
           ...
       # 统一替换与多余分隔符折叠
       result = ''.join(map(replace_insane, s))
       return result.replace('\0', '') or '_'

* **全角字符平滑映射**：在宽松模式下，冒号与斜杠被自动替换为对应的 Unicode 类似符号（如 ``\u29F8``），既保留了用户可视的语义，又杜绝了文件系统层面的路径截断错误；
* **严格限制模式 (`restricted=True`)**：强制将所有非 ASCII 字符与特殊符号通过 ``ACCENT_CHARS`` 转写表降级为标准英文字符集；
* **超长文件名安全截断 (`trim_file_name`)**：在扩展名之前对文件名进行安全长度切片，防止超过操作系统的 ``MAX_PATH``（260 字符）限制。

---
端到端文件名解析调用链与源码映射
---

.. code-block:: text
   :caption: prepare_filename 完整调用时序

   YoutubeDL                     prepare_filename()
       |                                |
       |-- _prepare_filename() -------->|
       |    |-- _outtmpl_expandpath()   | (环境变量展开并保护 % 与 $)
       |    |-- evaluate_outtmpl() ---->|
       |    |    |-- prepare_outtmpl()  | (双层正则解构、AST求值、修饰符编码)
       |    |    \-- escape_outtmpl() % | (Python 原生安全字典插值)
       |    |-- replace_extension() ----| (校准最终媒体容器扩展名)
       |    \-- trim_file_name ---------| (长文件名截断)
       |                                |
       \-- get_output_path() ---------->| (拼接 home/temp 目录并执行 sanitize_path)

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: Outtmpl 核心模块与源码行级对照
   :widths: 28 26 46
   :header-rows: 1

   * - 核心方法
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``prepare_outtmpl()``
     - ``yt_dlp/YoutubeDL.py:530-670``
     - 双层正则分词、AST 树遍历、算术求值与命令沙箱校验
   * - ``evaluate_outtmpl()``
     - ``yt_dlp/YoutubeDL.py:672-675``
     - 结合临时隔离字典执行最终字符串求值
   * - ``_prepare_filename()``
     - ``yt_dlp/YoutubeDL.py:677-710``
     - 扩展名动态替换、类型模板映射与文件名超长截断
   * - ``prepare_filename()``
     - ``yt_dlp/YoutubeDL.py:712-730``
     - 整合 ``paths`` 字典，输出跨平台安全的目标物理绝对路径
   * - ``sanitize_filename()``
     - ``yt_dlp/utils/_utils.py:340-390``
     - 平台非法字符过滤、重音转写、全角字形映射与空白折叠

***
小结与下章导读
***

本节系统剖析了 ``yt-dlp`` 输出模板解析引擎（Outtmpl）的底层机制，厘清了：
1. 双层正则表达式与空字符隔离编码如何保障 DSL 解析的确定性；
2. AST 字段树遍历与即时算术求值器如何赋能高表达力的动态路径组合；
3. 扩展修饰符矩阵（列表、JSON、Shell引用、单位换算）的底层实现；
4. 沙箱白名单机制如何有效防御 ``--exec`` 下潜在的命令注入漏洞。

在下一节（``04_download_archive_and_deduplication.rst``）中，我们将探讨物理文件生成后的状态持久化中枢——深度剖析 ``download_archive`` 下载历史归档、基于文件锁的跨进程并发安全控制与幂等去重状态机。
