from datetime import datetime

from exceptiongroup import catch
from fastapi import FastAPI, Depends
from sqlalchemy import create_engine, result_tuple
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker, Session

from pydantic import BaseModel

import logger_config
from logger_config import setup_logger
from config import settings
import model
from model import SvcId
from logger_api import log_requests
import logging

app = FastAPI()
setup_logger()
logger = logging.getLogger(__name__)
logger.info("fastapi start!")

engine = create_engine(settings.database_url)
sessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
app.middleware("http")(log_requests)

def get_db():
    db = sessionLocal()
    db.execute(text("SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    # 验证设置是否生效
    # result = db.execute(text("SELECT @@session.transaction_isolation")).scalar()
    # logger.info(f"当前隔离级别: {result}")  # 应输出 SERIALIZABLE
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
def app_startup():
    logger.info("app startup!")
    model.Base.metadata.create_all(bind=engine)


# @app.get("/")
# async def root():
#     return {"message": "Hello World"}
#
#
# @app.get("/hello/{name}")
# async def say_hello(name: str):
#     return {"message": f"Hello {name}"}


def alloc_new_ids(game_id: int, area_id: int, count: int, db: Session):
    new_ids = []  # 新申请id
    reuse_ids = []  # 重用id

    # 查询 svc_id 字段最大的记录
    max_item = db.query(SvcId).order_by(SvcId.svc_id.desc()).with_for_update().first()
    max_svc_id = max_item.svc_id if max_item else 0

    # 计算需要重复利用的id数量
    need_reuse_count = count - (settings.max_svc_id - max_svc_id)
    if need_reuse_count <= 0:
        new_ids = [max_svc_id + i for i in range(1, count + 1)]
    else:
        # 查询 need_reuse_count 个已删除的svc_id
        reuse_list = db.query(SvcId).filter(SvcId.delete_time != None
                     ).order_by(SvcId.svc_id.asc()).limit(need_reuse_count).with_for_update().all()
        if len(reuse_list) < need_reuse_count:
            raise Exception("数据库中可分配的进程实例id不足")

        # 重用svc_id 更新数据库
        for item in reuse_list:
            item.delete_time = None
            item.update_time = datetime.now()
            item.game_id = game_id
            item.area_id = area_id

        reuse_ids = [item.svc_id for item in reuse_list]
        for i in range(1, count - len(reuse_ids) + 1):
            new_ids.append(max_svc_id + i)

    # 写入新申请的svc_id
    for id in new_ids:
        # 插入
        db.add(SvcId(game_id=game_id, area_id=area_id, svc_id=id, create_time=datetime.now(), update_time=datetime.now()))

    new_ids.extend(reuse_ids)
    # 从小到大排序
    new_ids.sort()
    return new_ids


# class SvcIdQuery(BaseModel):
#     game_id: int
#     area_id: int
#
# @app.get("/svc_id/query")
# def svc_id_get(req: SvcIdQuery, db: Session = Depends(get_db)):
#     try:
#         # 查询数据库
#         db_items = db.query(SvcId).filter(SvcId.game_id == req.game_id, SvcId.area_id == req.area_id, SvcId.delete_time == None).all()
#         return {"svc_ids": [item.svc_id for item in db_items], "err_code": 0, "err_msg": ""}
#     except Exception as e:
#         return {"svc_ids": [], "err_code": 1, "err_msg": f"操作失败{e}"}


class SvcIdGet(BaseModel):
    game_id: int
    area_id: int
    count: int          # 数量等于0 不创建 否则未查到会创建

# 获取某个区服的所有进程实例id (如果有直接返回， 没有重新分配并返回)
@app.post("/svc_id/get")
def svc_id_get(req: SvcIdGet, db: Session = Depends(get_db)):
    try:
        # 查询数据库
        db_items = db.query(SvcId).filter(SvcId.game_id == req.game_id, SvcId.area_id == req.area_id, SvcId.delete_time == None).all()
        if len(db_items) > 0:
            return {"svc_ids": [item.svc_id for item in db_items], "err_code": 0, "err_msg": ""}

        if req.count == 0:
            return {"svc_ids": [], "err_code": 0, "err_msg": ""}
        else:
            # 申请进程id
            ids = alloc_new_ids(req.game_id, req.area_id, req.count, db)
            db.commit()
            return {"svc_ids": ids, "err_code": 0, "err_msg": ""}

    except Exception as e:
        db.rollback()
        return {"svc_ids": [], "err_code": 1, "err_msg": f"操作失败{e}"}



class SvcIdRecycle(BaseModel):
    game_id: int
    area_id: int

# 回收某个区服的所有进程实例id
@app.post("/svc_id/recycle")
def svc_id_recycle(req:SvcIdRecycle, db: Session = Depends(get_db)):
    try:
        # 查询数据库
        db_items = db.query(SvcId).filter(SvcId.game_id == req.game_id, SvcId.area_id == req.area_id, SvcId.delete_time == None).all()
        if len(db_items) == 0:
            return {"err_code": 0, "err_msg": ""}

        # 回收进程id
        for item in db_items:
            item.delete_time = datetime.now()
            item.update_time = datetime.now()

        db.commit()
        return {"err_code": 0, "err_msg": ""}

    except Exception as e:
        db.rollback()
        return {"err_code": 1, "err_msg": f"操作失败{e}"}


class SvcIdResize(BaseModel):
    game_id: int
    area_id: int
    resize: int

# 扩容或者缩容某个区服的进程实例id  返回操作后的实例id列表 (如果当前区服未分配进程id, 则不会进行任何扩容或者缩容操作)
@app.post("/svc_id/resize")
def svc_id_resize(req: SvcIdResize, db: Session = Depends(get_db)):
    try:
        # 查询数据库
        db_items = db.query(SvcId).filter(SvcId.game_id == req.game_id, SvcId.area_id == req.area_id, SvcId.delete_time == None).order_by(SvcId.svc_id.asc()).all()
        if len(db_items) == 0:
            return {"svc_ids": [], "err_code": 1, "err_msg": "当前区服未分配进程id，无法扩容或者缩容"}

        ids = [item.svc_id for item in db_items]
        if req.resize < 0 or len(db_items) == req.resize:
            return {"svc_ids": ids, "err_code": 0, "err_msg": ""}

        add_num = req.resize - len(db_items)
        if add_num < 0:
            # 缩容
            for item in db_items[add_num:]:
                ids.remove(item.svc_id)
                item.delete_time = datetime.now()
                item.update_time = datetime.now()
        else:
            # 扩容
            add_ids = alloc_new_ids(req.game_id, req.area_id, add_num, db)
            ids.extend(add_ids)
            ids.sort()

        db.commit()
        return {"svc_ids": ids, "err_code": 0, "err_msg": ""}
    except Exception as e:
        db.rollback()
        return {"svc_ids": [], "err_code": 2, "err_msg": f"操作失败{e}"}
