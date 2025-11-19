```shell
# 初始化新项目 (生成 pyproject.toml)
uv init <项目名>

# 或者在当前目录初始化
uv init

# 把 requirements.txt 中的依赖迁移到 pyproject.toml 并生成 uv.lock
uv add -r requirements.txt

# 查看所有可用的 Python 版本(uv 能自动安装官方预编译版本)
uv python list
 
# 查看系统中已安装的可用 Python 版本
uv python find

# 在当前目录下创建虚拟环境 
uv venv
 
# 使用指定解释器路径创建虚拟环境
uv venv <环境名> --python <解释器路径或者版本>
uv venv .venv --python 3.12.9

# 激活虚拟环境
source .venv/bin/activate

# 强制根据 toml 重新生成 lock 文件 (慎用，可能会升级包版本)
uv lock

# 同步所有依赖()
uv sync

# 同步主依赖
uv sync --no-default-groups

# 同步主依赖+dev依赖
uv sync --no-default-groups --group dev

# 同步依赖到当前激活的虚拟环境
uv sync --active

# 同步依赖到指定的虚拟环境
uv sync --python <解释器路径>

# 添加依赖(会自动执行uv lock, 并且更新project.toml)
uv add <包名>

# 删除依赖(会自动执行uv lock, 并且更新project.toml)
uv remove <包名>

# 升级依赖(会自动执行uv lock, 并且更新project.toml)
uv lock --upgrade-package <包名>

# 所有的依赖
uv pip list

# 强制重建环境(清理缓存并重新同步)
uv clean && uv sync

# 重建环境
rm -rf .venv && uv lock && uv sync

# 激活环境
source .venv/bin/activate

# 运行命令(会寻找当前文件夹下的.venv环境)
uv run <命令>

# 使用指定解释器运行命令
uv run --python <uv的解释器路径>

# 导出依赖到requirements.txt
uv pip freeze > requirements.txt

# PyCharm 兼容性
uv pip install pip setuptools wheel
```