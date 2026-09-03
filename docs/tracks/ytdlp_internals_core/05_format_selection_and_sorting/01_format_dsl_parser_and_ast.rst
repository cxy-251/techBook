========================================================================================
05.01 格式选择 DSL 语法解析器：Tokenize 词法流、布尔表达式与 AST 过滤树构建
========================================================================================

.. note:: 前置背景与上下文承接
   在前一模块中，我们全面解析了流媒体分片与底层网络协议（从单流 HTTP 断点续传到 Native HLS、MPEG-DASH XML 清单树与直播滑窗）。当 ``InfoExtractor`` 完成流媒体信息提取后，提取字典中往往包含几十种不同分辨率、不同编解码格式（H.264/AVC、VP9、AV1、AAC、Opus）、多语言音轨及封装容器的流变体列表。用户或下游调度器需要一种极为灵活、表达力极强且具备容错降级能力的语法来精准圈选所需轨道。``yt-dlp`` 彻底重构了流媒体选择引擎，推出了一套基于抽象语法树（AST）的声明式 **格式选择领域特定语言（Format Selection DSL）**。本节将深入剖析该 DSL 的词法切分、运算符优先级状态机、属性过滤正则引擎以及 AST 闭包编译流水线。

***
Format DSL 语言规范与设计哲学
***

在现代自适应流媒体（DASH / HLS）架构中，视频与音频通常采用独立分轨传输（Audio-only 与 Video-only）。一个完备的视频下载任务往往需要“选择最佳视频轨 + 选择最佳音频轨 + 降级兼容合并格式”。

.. code-block:: text
   :caption: Format DSL 表达式范例与拓扑语义

   典型格式表达式：
   "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

   语义分解：
   +-------------------------------------------------------------------------------+
   | 阶段 1: 尝试匹配 "bestvideo[height<=1080][ext=mp4] + bestaudio[ext=m4a]"      |
   |         (寻找 <=1080p 的 MP4 视频轨 与 M4A 音频轨 进行合并)                   |
   +---------------------------------------+---------------------------------------+
                                           | 若上述组合不存在 (返回空集)
                                           v 触发 "/" 降级运算符
   +-------------------------------------------------------------------------------+
   | 阶段 2: 尝试匹配 "best[ext=mp4]" (寻找已预混音的最高画质原生 MP4 格式)        |
   +---------------------------------------+---------------------------------------+
                                           | 若仍不存在
                                           v 触发 "/" 再次降级
   +-------------------------------------------------------------------------------+
   | 阶段 3: 兜底匹配 "best" (任意可用的最高质量格式)                              |
   +-------------------------------------------------------------------------------+

核心运算符优先级与结合性矩阵
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Format DSL 支持五种核心语法构件，其优先级由高到低排列如下：

.. list-table:: Format DSL 运算符语法与求值优先级
   :widths: 15 15 20 50
   :header-rows: 1

   * - 运算符
     - 语法名称
     - 结合性
     - 语义与行为
   * - ``[...]``
     - 属性过滤选择器
     - 左结合
     - 附加于原子选择器之后，基于元数据字段进行谓词过滤，支持多重串联（逻辑与）
   * - ``+``
     - 轨道合并运算符
     - 左结合
     - 将左侧选出的视频/音频集合与右侧选出的音频/视频集合进行笛卡尔积合并（``_merge``）
   * - ``/``
     - 首选降级运算符
     - 左结合
     - 短路选择（Pick-First）：依次评估左侧分支，若结果非空则直接返回，否则求值右侧分支
   * - ``,``
     - 序列收集运算符
     - 左结合
     - 多任务收集：将多个独立的格式选择结果连接为一个列表，下载所有匹配的格式
   * - ``(...)``
     - 分组括号
     - 不适用
     - 显式提升子表达式的求值优先级，改变默认的结合顺序

---
词法分析与 Tokenize 预处理流
---

``yt-dlp`` 巧妙地复用了 Python 标准库的 ``tokenize.tokenize`` 词法扫描器，将 DSL 文本解析为词法单元流（Token Stream）。

Python 3.12+ 词法兼容性 Hack
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Python 3.12 之前，形如 ``7_a`` 的标识符在特定的解析上下文中被容忍；但 Python 3.12 引入了更严苛的 PEP 684 词法分析器，将带有下划线的数字后置字母直接判定为非法的数字字面量，抛出 ``SyntaxError: invalid decimal literal``。由于 YouTube 等平台广泛存在形如 ``137_a``、``248-1`` 的格式 ID，``build_format_selector`` 引入了随机字符前缀混淆与逆向剥离机制：

.. code-block:: python

   # 1. 生成 32 字符随机字母前缀，使所有数字标识符在 tokenize 看来都成为普通合法 NAME
   prefix = ''.join(random.choices(string.ascii_letters, k=32))
   # 2. 将所有数字序列（如 137, 7_a）前置该前缀
   stream = io.BytesIO(re.sub(r'\d[_\d]*', rf'{prefix}\g<0>', format_spec).encode())
   # 3. 执行 tokenize，并在词法流生成后将 prefix 剥离还原
   tokens = list(_remove_unused_ops(
       token._replace(string=token.string.replace(prefix, ''))
       for token in tokenize.tokenize(stream.readline)))

运算符流清洗与连续标识符规约 (_remove_unused_ops)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

标准 ``tokenize`` 会将带有中划线或点号的复杂格式 ID（如 ``mp4-baseline-16x9``）拆解为多个独立 token：``[NAME('mp4'), OP('-'), NAME('baseline'), OP('-'), NAME('16x9')]``。

``_remove_unused_ops`` 生成器维护滑动窗口，将非保留控制符（不在 ``ALLOWED_OPS = ('/', '+', ',', '(', ')')`` 中且不在方括号 ``[]`` 过滤块内的符号）与相邻字符串粘合为单一的原子标识符：

.. code-block:: text
   :caption: Token 流清洗规约状态机

   原始 Token 流: [NAME("mp4"), OP("-"), NAME("dash"), OP("["), NAME("height"), OP("<="), NUMBER("720"), OP("]"), OP("/"), NAME("best")]
                                        |
                                        v _remove_unused_ops() 处理
   清洗后 Token 流: [NAME("mp4-dash"), OP("["), NAME("height<=720"), OP("]"), OP("/"), NAME("best")]

---
自顶向下递归下降语法分析与 AST 构建
---

语法解析器通过 ``_parse_format_selection`` 构建抽象语法树。AST 的节点由轻量级具名元组 ``FormatSelector`` 承载：

.. code-block:: python

   FormatSelector = collections.namedtuple('FormatSelector', ['type', 'selector', 'filters'])

AST 节点类型（Node Types）
~~~~~~~~~~~~~~~~~~~~~~~~~~

* **``SINGLE``**：原子选择器（叶子节点）。包含格式标识符字符串（如 ``bestvideo``、``137``、``mp4``）与附加的过滤器列表 ``filters``；
* **``GROUP``**：括号分组节点。包含一个完整的子 AST 树；
* **``MERGE``**：合并节点（二叉节点）。包含 ``(selector_1, selector_2)``；
* **``PICKFIRST``**：降级选择节点（二叉节点）。包含 ``(first_choice, second_choice)``；
* **``list``**：顶层序列列表，对应逗号 ``,`` 分隔的多格式集合。

递归下降解析状态机
~~~~~~~~~~~~~~~~~~

``_parse_format_selection`` 接收 ``TokenIterator`` 并通过状态标志（``inside_merge``、``inside_choice``、``inside_group``）以及单步回溯（``restore_last_token``）实现精确的优先级切分：

.. code-block:: python

   def _parse_format_selection(tokens, inside_merge=False, inside_choice=False, inside_group=False):
       selectors = []
       current_selector = None
       for type_, string_, start, _, _ in tokens:
           if type_ in [tokenize.NAME, tokenize.NUMBER]:
               current_selector = FormatSelector(SINGLE, string_, [])
           elif type_ == tokenize.OP:
               if string_ == ')':
                   if not inside_group:
                       tokens.restore_last_token()
                   break
               elif inside_merge and string_ in ['/', ',']:
                   tokens.restore_last_token()  # 退出 merge 递归，让更高层处理 '/' 或 ','
                   break
               elif inside_choice and string_ == ',':
                   tokens.restore_last_token()  # 退出 choice 递归
                   break
               elif string_ == ',':
                   selectors.append(current_selector)
                   current_selector = None
               elif string_ == '/':
                   first_choice = current_selector
                   second_choice = _parse_format_selection(tokens, inside_choice=True)
                   current_selector = FormatSelector(PICKFIRST, (first_choice, second_choice), [])
               elif string_ == '[':
                   if not current_selector:
                       current_selector = FormatSelector(SINGLE, 'best', [])  # 省略前缀时默认为 best
                   format_filter = _parse_filter(tokens)
                   current_selector.filters.append(format_filter)
               elif string_ == '(':
                   group = _parse_format_selection(tokens, inside_group=True)
                   current_selector = FormatSelector(GROUP, group, [])
               elif string_ == '+':
                   selector_1 = current_selector
                   selector_2 = _parse_format_selection(tokens, inside_merge=True)
                   current_selector = FormatSelector(MERGE, (selector_1, selector_2), [])
       if current_selector:
           selectors.append(current_selector)
       return selectors

---
属性过滤选择器 (_build_format_filter) 与运算符矩阵
---

当解析器在原子选择器后遇到方括号 ``[filter_spec]`` 时，调用 ``_build_format_filter`` 将过滤字符串动态编译为一个 Python 谓词函数 ``_filter(f) -> bool``。

数值型与存储大小比较运算符
~~~~~~~~~~~~~~~~~~~~~~~~~~

数值比较支持常用的 6 种二元关系符：``<``、``<=``、``>``、``>=``、``=``、``!=``。

.. code-block:: text
   :caption: 数值过滤器正则表达式匹配结构

   operator_rex:
   (?P<key>[\w.-]+)\s*(?P<op><|<=|>|>=|=|!=)(?P<none_inclusive>\s*\?)?\s*(?P<value>[0-9.]+(?:[kKmMgGtTpPeEzZyY]i?[Bb]?)?)

支持通过 ``parse_filesize`` 解析带有标准 SI/IEC 存储单位的字符串：
* ``[filesize>100M]``：过滤文件体积大于 $100 	imes 1000^2$ 字节的流；
* ``[filesize_approx<=1.5GiB]``：过滤预估体积小于等于 $1.5 	imes 1024^3$ 字节的流；
* ``[tbr>=5000]``：过滤总码率大于等于 5000 kbps 的流。

字符串高级匹配运算符
~~~~~~~~~~~~~~~~~~~~

针对编码、语言、容器等文本字段，提供丰富的字符串模式运算符：

.. list-table:: 字符串过滤运算符语义对照表
   :widths: 15 25 60
   :header-rows: 1

   * - 运算符
     - 内部实现
     - 行为与典型应用
   * - ``=``
     - ``operator.eq``
     - 精确全字匹配，如 ``[ext=mp4]``、``[vcodec=avc1.640028]``
   * - ``^=``
     - ``str.startswith``
     - 前缀匹配，如 ``[vcodec^=av01]``（匹配所有 AV1 编码变体）
   * - ``$=``
     - ``str.endswith``
     - 后缀匹配，如 ``[format_id$=dash]``（匹配所有以 dash 结尾的 ID）
   * - ``*=``
     - ``operator.contains``
     - 子串包含，如 ``[format_note*=HDR]``（包含 HDR 标记的流）
   * - ``~=``
     - ``re.search``
     - 正则表达式搜索，如 ``[language~=^(en|zh)]``（匹配英文或中文音轨）
   * - ``!=`` / ``!^=``
     - 否定逻辑
     - 前置 ``!`` 触发否定断言，如 ``[vcodec!=none]``（排除纯音频流）

空值容差操作符（``?`` 语义）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在实际网络抓取中，部分格式的元数据并不完整（例如服务端未声明 ``filesize`` 或 ``fps``）。
* 默认情况下，若待比较字段为 ``None``，比较直接返回 ``False``；
* 若在运算符后追加 ``?``（例如 ``[filesize>?100M]`` 或 ``[fps>=?60]``），当字段为 ``None`` 时谓词求值返回 ``True``（放行该格式），防止因信息缺失而误杀潜在的最优流。

---
AST 评估引擎与惰性执行管道 (_build_selector_function)
---

解析得到的 AST 树最终通过 ``_build_selector_function`` 递归编译为一个高阶闭包函数：

.. math::

   	ext{eval\_selector}: 	ext{Context} 	o 	ext{Generator}[	ext{FormatDict}]

.. code-block:: text
   :caption: AST 求值引擎闭包拓扑图

                  [PICKFIRST: /]
                 /              \
         [MERGE: +]          [SINGLE: best]
        /          \
   [SINGLE: bv]   [SINGLE: ba]
   (filter: h<=1080) (filter: ext=m4a)

1. 原子选择器 (SINGLE) 的求值与多维别名展开
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当原子为 ``best``、``worst``、``bv``、``ba``、``bv*``、``ba*`` 等关键字时，引擎执行正则分解与属性匹配：

.. code-block:: python

   # 正则分解关键字: (best|worst|b|w)(video|audio|v|a)?(*)?(.N)?
   # 例如: 'bv*' -> bw='b', type='v', mod='*', n=None
   #      'bestvideo.2' -> bw='b', type='video', mod=None, n=2 (选择次优流)
   mobj = re.match(r'(?P<bw>best|worst|b|w)(?P<type>video|audio|v|a)?(?P<mod>\*)?(?:\.(?P<n>[1-9]\d*))?$', format_spec)

别名匹配判定规则：
* ``bv`` / ``bestvideo``：要求 ``vcodec != 'none' and acodec == 'none'``（纯视频流）；
* ``ba`` / ``bestaudio``：要求 ``acodec != 'none' and vcodec == 'none'``（纯音频流）；
* ``bv*`` / ``bestvideo*``：要求 ``vcodec != 'none'``（包含纯视频流以及已带音频的完整流）；
* ``b`` / ``best``：要求 ``vcodec != 'none' and acodec != 'none'``（已混音的完整流）；
* ``format_idx``（如 ``.2``）：从排序后的候选流列表中选取第 2 个元素（实现次优流选取）。

2. 笛卡尔积合并与容器兼容性计算 (_merge)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于 ``MERGE (+)`` 节点，求值函数对左右子树的输出执行全排列笛卡尔积（``itertools.product``），并调用 ``_merge`` 构造复合格式字典：

.. code-block:: python

   def _merge(formats_pair):
       format_1, format_2 = formats_pair
       formats_info = []
       formats_info.extend(format_1.get('requested_formats', (format_1,)))
       formats_info.extend(format_2.get('requested_formats', (format_2,)))

       # 提取视频轨与音频轨列表
       video_fmts = [fmt for fmt in formats_info if fmt.get('vcodec') != 'none']
       audio_fmts = [fmt for fmt in formats_info if fmt.get('acodec') != 'none']

       # 计算目标合并容器扩展名 (mp4, mkv, webm)
       output_ext = get_compatible_ext(
           vcodecs=[f.get('vcodec') for f in video_fmts],
           acodecs=[f.get('acodec') for f in audio_fmts],
           vexts=[f['ext'] for f in video_fmts],
           aexts=[f['ext'] for f in audio_fmts],
           preferences=params.get('merge_output_format'))

       # 构建合成字典，汇总多轨特征
       return {
           'requested_formats': formats_info,
           'format_id': '+'.join(f['format_id'] for f in formats_info),
           'ext': output_ext,
           'protocol': '+'.join(determine_protocol(f) for f in formats_info),
           'filesize_approx': sum(f.get('filesize') or f.get('filesize_approx') or 0 for f in formats_info) or None,
           'tbr': sum(f.get('tbr') or 0 for f in formats_info),
           **video_metadata,
           **audio_metadata,
       }

3. 惰性求值与网络可下载性探测 (LazyList & _check_formats)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在通过 ``_filter`` 链式筛选后，输出结果被包装进 ``LazyList``。若用户启用了 ``--check-formats``，下载器仅在实际索引取值时发起微型 HEAD/Range 测试，探测目标分片是否存在 HTTP 403/404，遇不可用流时惰性跳过并自动向后顺延。

---
端到端格式选择架构图与源码映射
---

.. code-block:: text
   :caption: Format DSL 端到端编译与执行调用链

   用户输入 format_spec (例如 "bv*+ba/b")
                |
                v YoutubeDL.build_format_selector()
   +-------------------------------------------------------------------+
   | 1. 词法预处理:                                                    |
   |    - 随机前缀填充 (规避 Python 3.12 数字字面量语法限制)           |
   |    - tokenize.tokenize() 产生词法流                               |
   |    - _remove_unused_ops() 规约连字标识符                          |
   +---------------------------------+---------------------------------+
                                     |
                                     v _parse_format_selection() 递归下降
   +-------------------------------------------------------------------+
   | 2. 语法分析与 AST 构建:                                           |
   |    - 解析 [filter] -> _parse_filter()                             |
   |    - 解析 () -> GROUP                                             |
   |    - 解析 +  -> MERGE                                             |
   |    - 解析 /  -> PICKFIRST                                         |
   |    - 解析 ,  -> Sequence List                                     |
   +---------------------------------+---------------------------------+
                                     |
                                     v _build_selector_function()
   +-------------------------------------------------------------------+
   | 3. AST 闭包编译:                                                  |
   |    - 将每个节点编译为 generator(ctx) 闭包函数                     |
   |    - 编译 [filter] 谓词 -> _build_format_filter()                 |
   +---------------------------------+---------------------------------+
                                     |
                                     v 返回可执行 format_selector 实例
   YoutubeDL.process_video_result() 调用 selector(ctx)
                |
                v
   +-------------------------------------------------------------------+
   | 4. 运行时求值:                                                    |
   |    - 传入经过 FormatSorter 排序的 formats 列表                    |
   |    - 过滤链逐级筛选 -> 惰性求值 -> 笛卡尔积 _merge() 合并         |
   |    - 输出最终待下载格式字典列表 requested_formats                 |
   +-------------------------------------------------------------------+

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: 格式选择 DSL 解析与执行引擎核心模块与源码位置
   :widths: 30 26 44
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``build_format_selector()``
     - ``yt_dlp/YoutubeDL.py:2342-2545``
     - Format DSL 编译入口、词法分析、AST 构建与执行闭包生成
   * - ``_remove_unused_ops()``
     - ``yt_dlp/YoutubeDL.py:2360-2385``
     - 词法流清洗、非控制运算符与相邻字符粘合规约
   * - ``_parse_format_selection()``
     - ``yt_dlp/YoutubeDL.py:2387-2435``
     - 自顶向下递归下降语法分析器，构建 ``FormatSelector`` AST 树
   * - ``_build_format_filter()``
     - ``yt_dlp/YoutubeDL.py:2285-2340``
     - 属性过滤器正则表达式编译、数值单位解析与字符串高级匹配
   * - ``_build_selector_function()``
     - ``yt_dlp/YoutubeDL.py:2490-2560``
     - AST 节点求值闭包生成、别名展开、降级短路与惰性筛选
   * - ``_merge()``
     - ``yt_dlp/YoutubeDL.py:2437-2488``
     - 多轨笛卡尔积合并、元数据汇总与容器兼容性判定
   * - ``get_compatible_ext()``
     - ``yt_dlp/utils/_utils.py:3100-3135``
     - 音视频编解码器兼容性矩阵推导（MP4 vs WebM vs MKV）

***
小结与下章导读
***

本节详细解构了 ``yt-dlp`` 格式选择 DSL 的完整底层架构，厘清了：
1. Format DSL 语法体系与运算符优先级（``[]`` > ``+`` > ``/`` > ``,``）；
2. 词法分析层基于 ``tokenize`` 的清洗规约与针对 Python 3.12 语法的随机前缀隔离机制；
3. 递归下降语法分析器构建 ``SINGLE`` / ``GROUP`` / ``MERGE`` / ``PICKFIRST`` 抽象语法树（AST）的实现机理；
4. 属性过滤器（``_build_format_filter``）对大小单位、正则表达式及空值容差（``?``）的全面支持；
5. AST 求值闭包编译、别名展开与音视频多轨合并（``_merge``）。

然而，Format DSL 挑选出的“最佳流（best）”在很大程度上取决于传入的格式列表是如何排序的。在下一节（``05_format_selection_and_sorting/02_format_sorter_and_ranking.rst``）中，我们将深入剖析 ``yt-dlp`` 核心的 **``FormatSorter`` 多维度自适应权重排序算法**，揭秘其如何基于分辨率、码率、编解码器代际效率、HDR 色彩空间、音频采样率等 15+ 维特征对复杂流列表建立严格的全序排序模型。
