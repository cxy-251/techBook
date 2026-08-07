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

Part 6：Intermediate Representation and Program Lowering
--------------------------------------------------------

* `第026章：Intermediate Representation as Compiler Working Language <026-intermediate-representation-as-compiler-working-language.rst>`_；
* `第027章：High-Level IR vs Low-Level IR <027-high-level-ir-vs-low-level-ir.rst>`_；
* `第028章：Lowering as Controlled Loss of Abstraction <028-lowering-as-controlled-loss-of-abstraction.rst>`_；
* `第029章：IR Verification and Structural Invariants <029-ir-verification-and-structural-invariants.rst>`_；
* `第030章：Designing IR for Analysis and Transformation <030-designing-ir-for-analysis-and-transformation.rst>`_。

Part 7：Control Flow Graphs, Basic Blocks, and Program Structure
---------------------------------------------------------------

* `第031章：Basic Blocks as Straight-Line Code Regions <031-basic-blocks-as-straight-line-code-regions.rst>`_；
* `第032章：Control Flow Graphs and Branch Structure <032-control-flow-graphs-and-branch-structure.rst>`_；
* `第033章：Dominators, Loops, and Reachability <033-dominators-loops-and-reachability.rst>`_；
* `第034章：Structured Control Flow vs Unstructured Jumps <034-structured-control-flow-vs-unstructured-jumps.rst>`_；
* `第035章：Control Flow Evidence in Real Compiler Pipelines <035-control-flow-evidence-in-real-compiler-pipelines.rst>`_。

Part 8：Data Flow Analysis, Def-Use Chains, and Program Facts
------------------------------------------------------------

* `第036章：Program Facts and Fixed-Point Thinking <036-program-facts-and-fixed-point-thinking.rst>`_；
* `第037章：Reaching Definitions and Live Variables <037-reaching-definitions-and-live-variables.rst>`_；
* `第038章：Use-Def Chains and Value Tracking <038-use-def-chains-and-value-tracking.rst>`_；
* `第039章：Forward vs Backward Data Flow Analysis <039-forward-vs-backward-data-flow-analysis.rst>`_；
* `第040章：Data Flow as the Basis of Optimization <040-data-flow-as-the-basis-of-optimization.rst>`_。

Part 9：SSA Form and Modern IR Design
-------------------------------------

* `第041章：Static Single Assignment and Value Identity <041-static-single-assignment-and-value-identity.rst>`_；
* `第042章：Phi Nodes, Block Arguments, and Value Merging <042-phi-nodes-block-arguments-and-value-merging.rst>`_；
* `第043章：SSA Construction and Destruction <043-ssa-construction-and-destruction.rst>`_；
* `第044章：SSA-Based Optimizations <044-ssa-based-optimizations.rst>`_；
* `第045章：SSA as the Language of Modern Optimizers <045-ssa-as-the-language-of-modern-optimizers.rst>`_。

阅读方式
--------

每章依次保留“核心知识点”“关键路径”“概念辨析”和“本章结论”。阅读时先定位当前 representation、CFG 与 value identity，再沿 predecessor/successor、fact merge、transfer function、SSA definition/use、phi/block argument、dominance 和 memory/effect boundary 复盘事实如何形成，最后用 verifier、reachability、side-effect 与 conservative proof 检查优化是否合法。