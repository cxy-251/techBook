第136章：神经渲染
================

核心知识点
----------

神经渲染不是单一算法，而是一组可插入渲染管线的学习模块
   工程上至少要区分 neural scene representation、neural material、neural denoising、neural upscaling 与 inference runtime。它们分别替代或补充场景表示、材质求值、噪声重建、分辨率重建和 GPU 推理执行层。

判断 Neural Pass 的第一步是确认它替代什么传统对象
   如果模型替代 mesh/volume，就是场景表示问题；替代复杂 BRDF/texture graph，就是材质问题；替代滤波器和 temporal reconstruction，就是图像重建问题。模型没有明确替代对象时，很难定义输入、输出、质量指标和 fallback。

Neural Scene Representation 把空间内容编码进可学习参数
   NeRF、feature grid、Gaussian splatting 等方法用网络、feature 或 primitive 表达密度、颜色、辐射或视角相关外观。它们适合 novel view、扫描资产或高维场景表示，但局部编辑、重建资产导出和动态内容更新比传统 mesh 更困难。

Neural Material 围绕 Shading Point 工作
   输入仍然是位置、法线、视线、光照方向、UV、LOD 等，输出是反射、采样参数或材质 feature。它最适合压缩复杂 layered material 或高维外观，同时保留传统材质系统的 artist override 和 fallback。

Neural Denoising 处理低采样 Radiance 的方差
   输入通常包含 noisy radiance、albedo、normal、depth、roughness、motion vector 与 history，输出更稳定的 lighting/radiance buffer。Guide buffer 的空间、编码和时间对齐直接决定去噪质量。

Neural Upscaling 通过低分辨率输入重建高分辨率输出
   主渲染以较低 internal resolution 生成 color/depth/motion/exposure/jitter/history，upscaler 再恢复显示分辨率。收益来自降低 shading、ray tracing 与带宽成本，风险主要是 ghosting、disocclusion、透明/粒子和 history 不一致。

Inference Runtime 是真正进入帧预算的执行层
   模型权重、tensor layout、temporary memory、matrix acceleration、queue、barrier、resource binding 与 fallback 都属于 runtime。模型视觉效果再好，只要推理耗时、显存峰值或同步长尾不可控，就不适合实时 frame。

传统渲染与神经渲染的核心差异是“显式规则”与“训练分布”
   传统路径主要由 mesh、texture、shader、BVH 和明确状态决定；神经路径还受训练数据、模型版本、推理精度、分布外输入与历史反馈影响。调试对象因此从单纯资源/状态扩展到 feature buffer、model input/output 和训练覆盖。

训练数据必须与运行时输入契约一致
   Scene representation 需要多视角图像和 pose；material 需要材质样本及观察/光照条件；denoiser 需要 noisy/clean pair 与 guide；upscaler 需要低/高分辨率 pair、motion、depth、jitter、history 等。训练时缺失的变量，运行时就会成为不稳定输入。

Validation Render 比单纯 Loss 更重要
   训练 loss 下降只能证明目标函数被优化。应保留 held-out camera、动态镜头、透明对象、细纹理、曝光变化和不同材质条件，用实际 render 检查模型是否过拟合或引入 temporal artifact。

模型导出需要明确 Runtime Contract
   Export 至少应固定 model version、input/output tensor、精度、颜色空间、分辨率约束、feature mask、temporary memory、目标 backend 与 fallback。训练产物若缺少这些字段，就无法稳定进入引擎。

实时应用应一次只接入一个 Neural Pass
   先固定输入输出、debug view、reference/fallback、GPU timing 与 memory，再组合多个 neural pass。多个模型共享 depth、motion、exposure 和 history 时，单个模型正确不代表组合后仍正确。

性能权衡要看整个 Frame Graph
   Neural upscaling 节省主渲染成本却增加 inference；neural denoising 允许降低 ray count，却增加模型与 history 成本；neural material 减少纹理/BRDF 开销，也可能增加寄存器和矩阵计算。必须比较“被替代成本”与“新增推理/同步成本”。

Fallback 是设计的一部分
   模型加载失败、硬件不支持、显存不足或 frame budget 超标时，应能切回传统 TAAU、传统 denoiser、普通 PBR material、SSR/probe 或较低质量模型。Fallback 输出格式应尽量保持一致，避免重写后续 frame graph。

关键路径
--------

训练到运行时：

::

   define neural task
   → collect dataset + feature buffers
   → train model
   → validation renders
   → export runtime contract
   → load model/weights
   → bind frame resources
   → inference pass
   → compare output with reference/fallback

实时 Frame：

::

   scene / material data
   → classical rendering constraints
   → noisy / low-resolution buffers
   → neural denoise / material / upscale
   → post-process
   → present
   → current output becomes history

诊断：

::

   visual or performance failure
   → identify neural pass role
   → inspect model inputs
   → inspect feature alignment/history
   → inspect model output
   → compare traditional fallback
   → measure GPU time + temporary memory
   → decide fix, lower quality, or disable

概念辨析
--------

* **Neural Rendering 与 Generative Image Model**：前者进入明确渲染资源和 frame graph，后者可以只生成独立图像。
* **Neural Scene 与 Neural Material**：前者表达空间内容，后者只替代表面外观求值。
* **Denoising 与 Upscaling**：去噪主要恢复低采样信号，放大主要恢复空间分辨率；二者都可能使用 temporal history。
* **Training Cost 与 Runtime Cost**：训练成本发生在资产/模型生产阶段，runtime cost 直接进入每帧预算。
* **Model Quality 与 Pipeline Quality**：模型单独指标好，不代表与 motion、history、post-process 组合后的最终 frame 稳定。
* **Neural Path 与 Fallback Path**：神经路径是高质量或高效率实现，fallback 是平台/性能压力下保持正确输出的替代路径。

本章结论
--------

神经渲染应按“Traditional Role—Dataset—Model—Runtime Input/Output—Frame Graph—History—Evidence—Fallback”理解。工程重点不是给渲染器加一个 AI 模型，而是明确模型究竟替代哪段传统计算，让训练数据、运行时资源和质量指标使用同一契约，并证明它在目标硬件上真正缩短关键路径且能在失效时安全降级。