# techBook

Sphinx 站点,`.rst` 和 `.md` 文件共用同一套导航与主题（Furo）渲染。旧版本(纯 rst、无构建、Linux Kernel 学习路径)保存在远程分支 `backup20260903`。

## 本地预览

Python 环境由 [uv](https://docs.astral.sh/uv/) 管理,依赖锁定在 `uv.lock`,不使用 `pip`/`venv`。

```bash
uv sync
.venv/bin/sphinx-build -b html docs docs/_build/html
python3 -m http.server 8000 -d docs/_build/html
```

新增/修改依赖用 `uv add <package>` / `uv remove <package>`,会自动更新 `pyproject.toml` 和 `uv.lock`,两者都要提交。

## 目录结构

- `pyproject.toml` / `uv.lock` — Python 依赖声明与锁定文件(sphinx / myst-parser / furo)
- `docs/conf.py` — 唯一的 Sphinx 配置,`source_suffix` 同时接受 `.rst` 和 `.md`(经 `myst-parser` 解析)
- `docs/index.rst` — 站点根导航
- `docs/tracks/<topic>/` — 每个技术专著一个目录,内部按模块拆分小节,`index.rst` 做该专著的 toctree
- `docs/about.md` — 验证 md 渲染用的示例页

新增技术文章继续用 `.rst`;如果某些内容更适合用 Markdown 写,直接放 `.md` 文件,在对应 `index.rst` 的 `toctree` 里加一行文件名即可,不需要转换格式。
