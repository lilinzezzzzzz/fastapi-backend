import uvicorn

from internal.app import create_app

app = create_app()

if __name__ == "__main__":
    # 这里的配置要和你的命令行参数一致
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
