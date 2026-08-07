第041章：双向渲染技术
====================

核心知识点
----------

双向技术同时从相机端和光源端构造路径
   Camera subpath 从像素进入场景，light subpath 从光源向外传播。渲染器选择两条子路径上的顶点做连接，再通过 visibility、BSDF、geometry term 和 MIS weight 得到完整光路贡献。

BDPT 的目标是提高低概率高贡献路径的采样效率
   小光源、狭窄亮区和复杂室内间接光常难以从 camera side 随机命中；light side 却更容易先到达这些高能量区域。双向连接把两端优势放进同一 estimator。

``s,t`` 描述完整路径的连接策略
   ``s`` 表示使用 light subpath 的前缀长度，``t`` 表示使用 camera subpath 的前缀长度。同一条完整路径可能由多个 ``s,t`` 策略生成，因此不能把各策略贡献直接相加，必须通过 MIS 比较其采样概率。

Path vertex 是 BDPT 的核心数据结构
   每个顶点至少保存位置、法线、interaction 类型、throughput ``beta``、forward PDF、reverse PDF、delta 标记、connectible 标记和 path depth。BDPT 需要在路径生成后回看全部顶点，数据必须长期保留。

连接贡献由两端 throughput、散射函数和几何项共同决定
   General connection 通常包含 ``light beta × light BSDF × G(x,y) × camera BSDF × camera beta``，再乘 MIS weight。Visibility ray 负责检查两顶点之间是否无遮挡。

MIS 是双向技术稳定性的核心
   同一完整路径可能由 Path Tracing、显式 light sampling、Light Tracing 或 general BDPT connection 生成。MIS 根据各策略对当前路径的 PDF 分配权重，避免低概率策略偶然产生超大贡献。

所有 PDF 必须统一到同一 measure
   BSDF sampling 常给 solid-angle PDF，而 path-space 比较通常需要 area PDF。表面方向 PDF 转面积 PDF 时要乘接收端余弦并除以距离平方。Measure 混用会导致距离相关亮度漂移、斜面异常和 MIS weight 爆炸。

Geometry term 与 PDF 转换不能混为一谈
   ``G`` 描述物理路径的距离、朝向和 visibility；PDF conversion 描述某采样策略生成该路径的概率。二者都出现 cosine/distance²，但语义完全不同。

Delta 事件限制任意顶点连接
   理想镜面和理想折射的出射方向是离散确定的，任意两点直连通常不是合法散射事件。因此这类 vertex 要标记为 delta，并阻止 general connection。Rough glossy/glass 具有有限 lobe，才可正常评估 BSDF/PDF 做连接。

BDPT 对 rough caustics 更友好，对 sharp caustics 仍可能困难
   粗糙玻璃和 glossy 反射有非零方向分布，连接策略能提供有效样本；纯 specular chain 属于 delta path，通常更适合 Photon Mapping、MLT 或专门 caustic sampler。

双向技术应按同等时间或 ray budget 评价
   一个 BDPT sample 要生成两条子路径并枚举多种连接，单样本成本高于普通 Path Tracing。比较收益应看同样渲染时间下 direct/indirect/glossy/caustic AOV 的 variance，而不是只比 spp。

调试必须能看到策略级证据
   Strategy heatmap、MIS weight、path length、zero reason、PDF 和 visibility 结果，可以区分“没有采到路径”“连接被遮挡”“delta 不可连”“PDF 错误”和“MIS 权重异常”。

关键路径
--------

单个 BDPT sample：

::

   pixel / camera sample
   → 生成 camera subpath
   + sample light endpoint
   → 生成 light subpath
   → 保存每个 vertex 的 beta / pdfFwd / pdfRev / delta
   → 枚举 s,t 策略
   → 检查 connectible
   → eval 两端 BSDF
   → visibility ray
   → geometry term
   → 把各策略 PDF 转到统一 measure
   → MIS weight
   → film accumulate / splat

问题排查：

::

   输出 strategy heatmap
   → 检查 path vertex 字段
   → 检查 delta/connectible
   → 检查 visibility
   → 检查 forward/reverse PDF
   → 检查 solid-angle 到 area 转换
   → 检查 MIS weight
   → 分离 indirect / glossy / caustic AOV
   → 最后比较同等时间下 variance

概念辨析
--------

* **Camera subpath 与 light subpath**：前者从传感器采样 importance，后者从光源传播 radiance；二者方向和 endpoint PDF 语义不同。
* **BDPT 与 Light Tracing**：Light Tracing 主要从光源端向相机/film splat；BDPT 同时保留两端子路径并枚举连接策略。
* **BDPT 与 Path Tracing + NEE**：NEE 可视为某类低阶连接策略；BDPT 把更多 ``s,t`` 构造统一纳入 estimator。
* **Geometry term 与 visibility**：geometry term 包含距离和朝向，visibility 只是连接是否被遮挡，虽常一起计算但概念不同。
* **Forward PDF 与 reverse PDF**：前者是当前 random walk 的采样概率，后者用于评价反方向替代策略，是 MIS 比较的重要数据。
* **Delta 与 glossy**：delta lobe 只在离散方向有概率，不能任意连接；glossy lobe 有有限宽度，可以评价连接方向的 BSDF/PDF。
* **BDPT 与 Photon Mapping**：BDPT 直接构造完整路径并用 MIS 加权；Photon Mapping 存储 light-side 样本后做空间密度估计，后者更容易处理某些 sharp caustics。
* **Sample count 与 sample efficiency**：BDPT 单样本更贵，应看单位时间误差下降，而非简单比较每像素样本数。

本章结论
--------

双向技术的稳定模型是“camera subpath + light subpath + 合法连接 + 统一 measure 的 MIS”。它特别适合小光源、室内强间接和部分 glossy 困难路径；对纯 specular chain 要识别 delta 边界。实现时最关键的是保存完整 path vertex 数据、正确转换 forward/reverse PDF，并让每个 ``s,t`` 策略和 MIS weight 都可视化，否则画面噪声很难回溯到具体路径问题。