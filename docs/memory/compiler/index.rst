Compiler 必背课本
=================

本目录与 AIBook 的 ``docs/Compiler`` 一一对应。AIBook 保留完整讲解、案例、源码和实验，这里只保留每章稳定、必须掌握、可以直接复习的知识模型。

Part 1：Compiler Worldview and Engineering Mental Model
--------------------------------------------------------

* `第001章：Compiler Transformation Model <001-compiler-transformation-model.rst>`_；
* `第002章：Source Code as a Structured System <002-source-code-as-a-structured-system.rst>`_；
* `第003章：Compilation as a Sequence of Representations <003-compilation-as-a-sequence-of-representations.rst>`_；
* `第004章：Interpreter, Compiler, Transpiler, and JIT <004-interpreter-compiler-transpiler-and-jit.rst>`_；
* `第005章：Compiler Correctness, Performance, and Developer Experience <005-compiler-correctness-performance-and-developer-experience.rst>`_。

Part 2：Source Text, Tokens, and Lexical Analysis
-------------------------------------------------

* `第006章：Source Text as Raw Characters <006-source-text-as-raw-characters.rst>`_；
* `第007章：Tokens as the First Structured Representation <007-tokens-as-the-first-structured-representation.rst>`_；
* `第008章：Lexical Rules, Keywords, Identifiers, and Literals <008-lexical-rules-keywords-identifiers-and-literals.rst>`_；
* `第009章：Whitespace, Comments, Newlines, and Layout-Sensitive Syntax <009-whitespace-comments-newlines-and-layout-sensitive-syntax.rst>`_；
* `第010章：Lexer Errors, Diagnostics, and Source Locations <010-lexer-errors-diagnostics-and-source-locations.rst>`_。

Part 3：Grammar, Parsing, and Abstract Syntax Trees
---------------------------------------------------

* `第011章：Grammar as the Shape of Valid Programs <011-grammar-as-the-shape-of-valid-programs.rst>`_；
* `第012章：Parsing Token Streams into Structure <012-parsing-token-streams-into-structure.rst>`_；
* `第013章：Parse Trees vs Abstract Syntax Trees <013-parse-trees-vs-abstract-syntax-trees.rst>`_；
* `第014章：Operator Precedence, Associativity, and Ambiguity <014-operator-precedence-associativity-and-ambiguity.rst>`_；
* `第015章：Parser Error Recovery and Developer Feedback <015-parser-error-recovery-and-developer-feedback.rst>`_。

Part 4：Semantic Analysis, Symbol Tables, and Scopes
----------------------------------------------------

* `第016章：Names, Bindings, and Program Meaning <016-names-bindings-and-program-meaning.rst>`_；
* `第017章：Symbol Tables and Scope Chains <017-symbol-tables-and-scope-chains.rst>`_；
* `第018章：Declarations, Definitions, and Resolution <018-declarations-definitions-and-resolution.rst>`_；
* `第019章：Modules, Imports, and Visibility Rules <019-modules-imports-and-visibility-rules.rst>`_；
* `第020章：Semantic Errors Beyond Syntax <020-semantic-errors-beyond-syntax.rst>`_。

Part 5：Type Systems, Type Checking, and Type Inference
-------------------------------------------------------

* `第021章：Types as Compile-Time Program Facts <021-types-as-compile-time-program-facts.rst>`_；
* `第022章：Static Typing, Dynamic Typing, and Gradual Typing <022-static-typing-dynamic-typing-and-gradual-typing.rst>`_；
* `第023章：Type Checking Expressions, Statements, and Functions <023-type-checking-expressions-statements-and-functions.rst>`_；
* `第024章：Generics, Templates, and Parametric Polymorphism <024-generics-templates-and-parametric-polymorphism.rst>`_；
* `第025章：Type Inference and Constraint Solving <025-type-inference-and-constraint-solving.rst>`_。

阅读方式
--------

每章依次保留“核心知识点”“关键路径”“概念辨析”和“本章结论”。阅读时先定位当前表示和对象，再沿转换路径复盘语义保持与新增约束，最后用概念边界检查判断是否准确。
