from fastapi import FastAPI

# 初始化应用
app = FastAPI(title="Luck的树莓派人脸识别接口")

@app.get("/")
async def read_root():
    return {"status": "success", "device": "Raspberry Pi 3b+", "message": "FastAPI 运行正常"}

@app.get("/check")
async def check_env():
    # 这里可以测试你的依赖是否正常
    import numpy as np
    return {"numpy_version": np.__version__, "info": "环境检测通过"}