import asyncio

import uvicorn

from internal.app import create_app

app = create_app()

if __name__ == "__main__":
    # 1. 创建配置对象 (参数和 uvicorn.run 一样)
    config = uvicorn.Config("main:app", host="0.0.0.0", port=8080, reload=False)

    # 2. 实例化服务器
    server = uvicorn.Server(config)

    # 3. 【关键步骤】手动运行 asyncio，不传 loop_factory 参数
    # 这样 PyCharm 的调试器就能正常接管，不会报错了
    asyncio.run(server.serve())
