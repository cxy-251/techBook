# 关于本站

这个页面是用 **Markdown** 写的，用来验证 techBook 的 Sphinx 站点可以让 `.rst` 和 `.md` 文件共同渲染在同一套导航和主题里。

- 左侧目录里的技术专著（编译器、C++/STL、CPython、操作系统……）全部是 `.rst`
- 这一页是 `.md`，通过 [MyST-Parser](https://myst-parser.readthedocs.io/) 解析
- 两者共用同一个 `conf.py`、同一套主题（[Furo](https://pradyunsg.me/furo/)）、同一个左侧导航树

以后新写的技术文章，可以继续用 `.rst`；如果某些内容更适合用 Markdown 写（比如从别处迁移过来的笔记），直接放 `.md` 文件、在某个 `index.rst` 的 `toctree` 里加一行文件名即可，不需要转换格式。

```python
# 代码块在 Markdown 里也能正常高亮
def hello():
    return "rst 和 md 在这里是平等公民"
```
