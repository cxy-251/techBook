第006章：Source Text as Raw Characters
======================================

核心知识点
----------

* 编译器接收源码时，最底层对象是 ``byte stream``；编码规则把 bytes 解码为字符序列，lexer 才能继续识别 token。
* 源码位置至少要区分 byte offset、字符/code point 位置和用户可见列宽；内部定位通常优先保存稳定的 byte offset。
* 文件身份、原始字节、解码规则、字符缓冲区和 line table 共同构成 source text 层的基础状态。
* UTF-8、BOM、CRLF/LF、Unicode 组合字符和规范化策略都可能改变扫描边界、列号和标识符比较结果。
* source text 层的核心职责不是决定关键字或语法，而是把输入收敛成可扫描、可回溯、可诊断的可信文本。

关键路径
--------

* 文件系统/编辑器缓冲区 → 读取原始 bytes → 确定编码 → 解码字符 → 建立文件身份与 offset 映射 → 建立 line table → 交给 lexer。
* 诊断定位路径：``FileID + byte offset`` → line table → 行号/列号 → 原始源码切片 → 用户可见 source range。
* 换行处理需要在逻辑换行和原始字节之间保持映射；即使内部把 CRLF 归一成一个换行，诊断仍必须回到正确 byte range。
* Unicode 名字是否归一化、按哪种 normalization form 比较，是语言规则；source text 层必须先保留准确字符序列和原始位置证据。

概念辨析
--------

* **byte 与 character**：byte 是文件输入单位；character/code point 是解码结果，二者不能按一一对应假设处理 UTF-8。
* **code point 与显示列**：一个 code point 不一定对应一个用户可见字符宽度；组合字符和宽字符会让显示列与 byte offset 分离。
* **原始文本与词法语义**：字符 ``=``、换行或名字片段在这一层只是输入；它们的 token 身份由 lexer 决定。
* **规范化与保留原样**：规范化便于比较，但可能改变字符序列；实现必须明确比较形式与诊断显示形式的责任边界。

本章结论
--------

编译的第一步是把不可靠的源码 bytes 转换为可定位、可诊断、可稳定扫描的文本视图。排查源码输入问题时，应依次检查文件身份、编码、换行与 Unicode 处理、byte offset 映射和显示列规则。