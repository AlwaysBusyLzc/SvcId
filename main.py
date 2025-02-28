from fastapi import FastAPI
import logger_config
from logger_config import setup_logger

app = FastAPI()
logger = setup_logger()
logger.info("fastapi start!")

# @app.get("/")
# async def root():
#     return {"message": "Hello World"}
#
#
# @app.get("/hello/{name}")
# async def say_hello(name: str):
#     return {"message": f"Hello {name}"}


# 获取某个区服的所有进程实例id
@app.post("/svc_id/get")
def svc_id_get(game_id: int, area_id: int, count: int):
    return {"area_ids": [1, 2, 3]}

# 回收某个区服的所有进程实例id
@app.post("/svc_id/recycle")
def svc_id_recycle(game_id: int, area_id: int):
    return {"area_ids": [1, 2, 3]}

# 扩容或者缩容某个区服的进程实例id
@app.post("/svc_id/resize")
def svc_id_resize(game_id: int, area_id: int, resize: int):
    return {"area_ids": [1, 2, 3]}

