```shell
迁移
uv add -r requirements.txt

显示所有可安装
uv python list
 
显示已经安装的版本
uv python find
 
创建虚拟环境
uv venv <环境名> --python <解释器路径或者版本>
uv venv .venv --python 3.12.9

激活虚拟环境
source .venv/bin/activate

同步所有依赖(团队中其他成员修改了依赖，相当于go mod tidy)
uv sync
同步主依赖
uv sync --no-default-groups
同步主依赖+dev依赖
uv sync --no-default-groups --group dev

同步依赖到当前激活的虚拟环境
uv sync --active

同步依赖到指定的虚拟环境
uv sync --python <解释器路径>

添加依赖(会自动执行uv lock, 并且更新project.toml)
uv add <包名>

删除依赖(会自动执行uv lock, 并且更新project.toml)
uv remove <包名>

升级依赖(会自动执行uv lock, 并且更新project.toml)
uv lock --upgrade-package <包名>

所有的依赖
uv pip list

清理缓存
uv clean

重建环境
rm -rf .venv && uv sync

激活环境
source .venv/bin/activate

运行命令(需要激活虚拟环境 source .venv/bin/activate)
uv run <命令>

导出依赖到requirements.txt
uv pip freeze > requirements.txt

Pycharm识别虚拟环境
uv pip install pip setuptools wheel
```