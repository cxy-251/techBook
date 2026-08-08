第096章：From Python Source to Tokens
=====================================

核心知识点
----------

* Python 源文件首先是字节序列。CPython 前端必须先确定源码编码并解码成 Unicode 文本，之后 tokenizer 才能按字符规则工作。
* 未显式声明编码时默认使用 UTF-8；编码声明和 UTF-8 BOM 会影响最初的解码边界。编码错误发生在 token stream 和 AST 之前。
* Tokenization 把连续字符流切成 parser 可消费的 token stream。Token 通常携带类型、原始文本、起止位置以及所在源码行等信息。
* Tokenizer 已经替 parser 完成大量局部字符判断，例如名字、数字、字符串、操作符、分隔符和多字符操作符的边界识别。
* Python 的缩进不是纯排版。Tokenizer 维护 indentation stack，把缩进增加转成 ``INDENT``，缩进回退转成一个或多个 ``DEDENT``。
* ``NEWLINE`` 表示一个逻辑语句行结束；括号内换行、空行等不会终止语句的换行通常以非终止换行形态处理。物理行和逻辑行必须区分。
* 括号嵌套会抑制普通换行的语句终止作用，因此列表、调用和表达式可以在括号内自然跨行。
* 缩进回退必须回到 indentation stack 中已经存在的层级；非法缩进、Tab/space 歧义可在 parser 建立 AST 之前失败。
* 在公开 token 视图中，许多关键字仍可以表现为名字类 token，真正语法角色由 parser 根据 grammar/context 决定。Soft keyword 更说明“token 类别”和“语法身份”不是同一层事实。
* Token stream 保留源码位置，是后续 SyntaxError、工具链、格式化、静态分析和源码映射的重要证据。
* 编译表示在这一阶段发生第一次结构化跃迁：原始文本中的空白和字符被压成 token 边界、逻辑行与缩进结构。

关键路径
--------

源码进入前端：

::

   .py source bytes
   → detect source encoding
   → decode to Unicode text
   → normalize line/input state
   → tokenizer scans characters
   → emit names/literals/operators/layout tokens
   → token stream with source locations
   → parser

缩进结构：

::

   beginning of logical line
   → measure indentation
   → compare with indentation stack top
   → greater: push + INDENT
   → equal: no layout token
   → smaller: pop + DEDENT until matched
   → mismatch: indentation error

概念辨析
--------

* **Source bytes 与 source text**：前者属于文件编码层，后者是解码后的 Unicode 字符序列；tokenizer 主要工作在后者上。
* **Physical line 与 logical line**：物理行由文件换行决定，逻辑行由括号、续行和 Python 语句规则共同决定。
* **NEWLINE 与普通换行**：``NEWLINE`` 代表语句级逻辑结束，括号内部等位置的换行不一定终止语句。
* **Whitespace 与 layout syntax**：普通分隔空白可以被忽略，行首缩进会被结构化成 ``INDENT/DEDENT`` 并直接参与语法。
* **Token kind 与 keyword role**：tokenizer 先识别词法单位，parser 再根据 grammar 判断该词在当前上下文是不是关键字或 soft keyword。

本章结论
--------

Python 前端的第一条稳定路径是 ``Source Bytes → Unicode Text → Tokenizer → Token Stream``。Python 的空白敏感性并不是 parser 临时读取空格得到的，而是在 tokenization 阶段就通过 ``INDENT/DEDENT/NEWLINE`` 被转换成明确的结构证据。