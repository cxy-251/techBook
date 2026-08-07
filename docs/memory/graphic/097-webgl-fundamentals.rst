第097章：WebGL 基础
==================

核心知识点
----------

WebGL 是浏览器中的 GPU 状态机接口
   ``canvas`` 提供显示表面，``WebGLRenderingContext/WebGL2RenderingContext`` 保存当前 program、buffer、texture、framebuffer、viewport、depth/blend/cull 等状态，浏览器再把命令翻译到平台图形后端。Draw 使用提交瞬间的当前状态。

WebGL 同时受图形 API 与浏览器生命周期约束
   除 shader、buffer、texture 外，还必须处理资源加载、CORS、设备像素比、页面 resize、tab 可见性、context loss 与浏览器合成。原生 OpenGL 的状态问题和 Web 平台事件问题会在同一帧中汇合。

Context 创建阶段决定基础能力与默认 Drawing Buffer
   ``alpha``、``depth``、``stencil``、``antialias``、``powerPreference`` 等属性影响默认 framebuffer、内存和合成路径。实际 WebGL 版本、extension 与 limit 必须在启动时查询并归一化成 renderer profile。

Program 是 Vertex/Fragment Shader 的链接结果
   Shader 先 compile，再 link 成 program。Compile 成功只说明单 stage 语法合法；link 还要验证 varying/interface。运行时还必须保证当前 program、attribute location、uniform location 和 texture unit 与资源一致。

Vertex Input 的关键是 Buffer 与 Attribute 解释关系
   ``ARRAY_BUFFER`` 只是当前绑定，``vertexAttribPointer`` 才记录 location、format、stride、offset 与 buffer 来源，``enableVertexAttribArray`` 决定 attribute 是否逐顶点读取。几何消失或 UV 错乱优先检查这一层。

Sampler Uniform 保存的是 Texture Unit 编号
   ``sampler2D`` uniform 的值通常是 0、1、2 等 unit index；实际 texture object 通过 ``activeTexture`` + ``bindTexture`` 绑定到对应 unit。纹理内容正确，不代表 shader 正在采样正确 unit、target 或 mip。

Drawing Buffer 尺寸与 CSS 尺寸必须分开管理
   ``canvas.clientWidth/clientHeight`` 是 CSS 像素，``canvas.width/height`` 是实际 drawing buffer 像素。Resize 时应结合 DPR 更新 drawing buffer，并同步 ``gl.viewport``；否则容易出现模糊、拉伸和覆盖区域错误。

WebGL 是状态机，Pass 间状态污染是高频错误
   Depth、blend、cull、viewport、scissor、program、texture unit 等状态会持续存在。2D UI、透明物体与 3D pass 应在入口显式声明需要的状态，不能依赖上一批 draw 留下的值。

能力与扩展必须按 Profile 选择路径
   WebGL 1、WebGL 2 与 extension 覆盖不同能力。最大纹理尺寸、纹理单元、vertex attribute、precision、renderbuffer 限制等都可能随设备变化。增强路径应基于查询结果开启，缺失时走 fallback。

Context Loss 是 GPU 资源的全局失效事件
   ``webglcontextlost`` 后旧 ``WebGLBuffer/WebGLTexture/WebGLProgram`` 等句柄不能继续使用。CPU 侧应保留 mesh 数据、图片来源、shader source 和材质描述，恢复后按依赖重新创建 GPU 资源。

WebGL 性能先看主线程与提交，再看 GPU
   Draw 数量、状态切换、帧内 texture upload、同步查询、drawing buffer 分辨率和 fragment shader 成本都会影响帧时间。频繁 ``getError/getParameter/readPixels`` 等同步入口应避免留在生产热路径。

关键路径
--------

WebGL 初始化：

::

   canvas
   → getContext(webgl/webgl2)
   → query version / limits / extensions
   → compile shaders
   → link program
   → create buffers / textures
   → resolve attribute / uniform locations
   → configure render state

一次纹理 Draw：

::

   bind program
   → bind vertex/index buffers
   → configure/enable attributes
   → set uniforms
   → active texture unit
   → bind texture + sampler parameters
   → set viewport / depth / blend / cull
   → drawElements / drawArrays
   → drawing buffer
   → browser compositor

Resize / 恢复：

::

   CSS size / DPR changed
   → resize canvas drawing buffer
   → update viewport / projection
   → render

   context lost
   → stop GPU submission
   → keep CPU asset descriptions
   → context restored
   → recreate program / buffers / textures / state
   → resume rendering

概念辨析
--------

* **Canvas 与 Drawing Buffer**：canvas 是 DOM 显示元素，drawing buffer 是 WebGL 真正写入的像素缓冲。
* **CSS Size 与 Buffer Size**：前者决定页面布局，后者决定 GPU 实际渲染分辨率。
* **Shader 与 Program**：shader 是单 stage 编译对象，program 是多个 stage 链接后的可执行组合。
* **Buffer Binding 与 Attribute Binding**：绑定 buffer 只选当前对象，attribute pointer 才定义顶点数据解释方式。
* **Texture Object 与 Texture Unit**：texture 保存图像，unit 是 shader sampler 间接指向资源的绑定槽。
* **WebGL 1/2 与 Extension**：版本提供能力基线，extension 提供额外能力，最终仍需查询 limit 与实际支持。
* **Context Lost 与普通资源释放**：普通释放影响单个对象，context lost 让整个 context 内 GPU 资源失效并要求重建。

本章结论
--------

WebGL 应按“Canvas/Context—Program—Vertex Input—Uniform/Texture Unit—Draw State—Drawing Buffer—Browser Composite”理解。黑屏先查 program、attribute、viewport 与 draw 参数；错纹理查 sampler unit、texture completeness 与 UV；resize 问题查 CSS size、DPR、drawing buffer 和 viewport；随机恢复失败则回到 context loss 的资源重建链。稳定 WebGL 渲染器的关键，是把 OpenGL 式持续状态和浏览器式生命周期同时做成可检查的契约。