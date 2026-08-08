HTML Tokenization, Parsing, and DOM Construction
================================================

核心知识点
----------

* ``text/html`` 响应先经过字符解码，再进入 tokenization 和 tree construction，最终生成 ``Document`` 与 DOM tree。
* token 是 HTML parser 的中间对象，包含 start tag、end tag、character、comment、DOCTYPE 等；token 本身还不等于 DOM 节点位置。
* DOM 构造是增量的：网络字节分块到达时，parser 可以持续创建节点，不必等待完整文档下载完成。
* HTML parser 维护 insertion mode、open element stack 等状态，同一个 token 在不同上下文中可能产生不同树结构。
* HTML 具有标准化错误恢复规则；源码中的错误嵌套、缺失结束标签和表格异常结构可能被修复成另一棵 DOM tree。
* View Source 展示原始输入，Elements 展示解析和运行时修改后的 DOM；两者不是同一层证据。

关键路径
--------

文档构造主路径：

``HTTP response bytes → character decoding → tokenization → tree construction → Document → DOM tree``

增量解析：

``Network chunk → parser state → token → node insertion → resource discovery / script-visible DOM``

结构异常排查：

``响应 HTML → token/解析上下文 → parser error recovery → 最终 DOM → CSS/JS/Hydration``

概念辨析
--------

* **HTML Source vs DOM**：源码是服务器或静态文件发送的文本；DOM 是浏览器按解析算法构造的运行时对象树。
* **Tokenization vs Tree Construction**：前者识别语法 token；后者结合 parser state 决定节点创建和插入位置。
* **缩进结构 vs DOM 结构**：源码缩进只服务人类阅读，最终父子关系由 HTML parsing algorithm 决定。
* **解析错误 vs 解析失败**：HTML 通常会按标准错误恢复继续生成 DOM，不代表输入结构正确。
* **DOM 节点 vs 视觉对象**：DOM 只描述文档对象关系，是否参与布局和绘制还要经过 CSS 与后续渲染阶段。

本章结论
--------

HTML parser 把网络文本转换成浏览器可执行、可查询、可修改的文档对象。排查 DOM、SSR、streaming 或 hydration 结构问题时，应把原始 HTML、tokenization、tree construction 和最终 DOM 分开观察，而不是假设浏览器机械复制源码结构。