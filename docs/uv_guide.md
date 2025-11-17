````markdown
# 🐍 Python 环境管理指南（使用 UV）

> 统一开发与部署流程的现代 Python 环境管理方案  
> 适用于个人开发、团队协作、Docker 构建与 CI/CD 场景
> 需要手动维护pyproject.toml
---

## 🧩 一、环境初始化

```bash
# 创建虚拟环境（指定 Python 版本）
uv venv .venv --python 3.12
uv pip install pip setuptools wheel
# 激活环境
source .venv/bin/activate     # Linux / macOS
.venv\Scripts\activate        # Windows
````

> 💡 使用 `uv python list` 可以查看可用解释器版本。

---

## 🧑‍💻 二、开发阶段常用命令

| 目标         | 命令                                                  | 说明                                                 |
| ---------- | --------------------------------------------------- | -------------------------------------------------- |
| **安装全部依赖** | `uv sync`                                           | 根据 `pyproject.toml` / `uv.lock` 同步依赖。若锁文件缺失，会自动生成。 |
| **添加新依赖**  | `uv add <包名>`                                       | 添加依赖并自动更新锁文件与虚拟环境。                                 |
| **移除依赖**   | `uv remove <包名>`                                    | 从项目移除依赖并更新锁文件。                                     |
| **更新依赖版本** | `uv lock && uv sync`                                | 重新解析依赖树并同步最新版本。                                    |
| **查看所有依赖** | `uv pip list`                                       | 列出当前环境安装的包。                                        |
| **导出依赖列表** | `uv export --output-file requirements.txt --frozen` | 导出带哈希值的冻结依赖。                                       |
| **清理缓存**   | `uv clean`                                          | 删除缓存与构建产物，保持环境干净。                                  |

---

## 🚀 三、部署与构建阶段命令

| 目标               | 命令                                 | 说明                                          |
| ---------------- | ---------------------------------- | ------------------------------------------- |
| **严格按锁文件安装依赖**   | `uv sync --locked`                 | 仅根据 `uv.lock` 安装，禁止重新解析。适用于部署、Docker、CI/CD。 |
| **重建干净环境**       | `rm -rf .venv && uv sync --locked` | 删除旧虚拟环境并精确重建。                               |
| **Docker 构建时使用** | `RUN uv sync --locked`             | 在镜像构建中快速还原稳定依赖。                             |
| **验证依赖一致性**      | `uv pip list`                      | 比对当前环境与锁文件中的版本。                             |

---

## 🧠 四、核心命令对照总结

| 命令                 | 是否解析依赖 | 是否更新锁文件 | 是否安装依赖 | 典型用途       |
| ------------------ | ------ | ------- | ------ | ---------- |
| `uv lock`          | ✅ 是    | ✅ 是     | ❌ 否    | 生成或更新锁文件   |
| `uv sync`          | ✅ 可能   | ✅ 可能    | ✅ 是    | 安装依赖并保持同步  |
| `uv sync --locked` | ❌ 否    | ❌ 否     | ✅ 是    | 部署阶段严格重现环境 |
| `uv add <pkg>`     | ✅ 是    | ✅ 是     | ✅ 是    | 添加依赖并立即安装  |
| `uv remove <pkg>`  | ✅ 是    | ✅ 是     | ✅ 是    | 移除依赖并更新锁文件 |

---

## 🧬 五、推荐使用模式

**开发阶段**

```bash
uv add fastapi
uv lock && uv sync
```

**部署 / CI / Docker 阶段**

```bash
uv sync --locked
```

---

## 🔧 六、辅助命令

| 命令                    | 作用                         |
| --------------------- | -------------------------- |
| `uv python list`      | 显示可用 Python 解释器版本          |
| `uv python find`      | 显示当前虚拟环境的解释器路径             |
| `uv export --dev`     | 导出包含开发依赖的 requirements.txt |
| `uv sync --reinstall` | 强制重新安装所有包（即便版本相同）          |

---

## 🧭 七、命令行为类比（对标 Go 工具链）

| 概念     | UV                 | Go                      |
| ------ | ------------------ | ----------------------- |
| 依赖声明   | `pyproject.toml`   | `go.mod`                |
| 锁定依赖   | `uv.lock`          | `go.sum`                |
| 添加依赖   | `uv add <pkg>`     | `go get <pkg>`          |
| 更新依赖   | `uv lock`          | `go mod tidy`           |
| 安装依赖   | `uv sync`          | `go mod download`       |
| 严格复现环境 | `uv sync --locked` | `go mod download`（锁定版本） |

---

## 🪶 八、总结理念

> * **开发时灵活，部署时确定。**
> * `uv lock`：定义依赖的世界。
> * `uv sync`：让世界与定义一致。
> * `uv sync --locked`：冻结世界，确保可重现。

---

*维护环境时不需要魔法，只需要一个好习惯：
锁定、同步、重现。*