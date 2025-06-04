from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, wait_fixed
from sqlalchemy.exc import DBAPIError, OperationalError, TimeoutError, InternalError
from contextlib import contextmanager
from functools import partial

from datetime import datetime

import uvicorn
from exceptiongroup import catch
from fastapi import FastAPI, Depends
from sqlalchemy import create_engine, result_tuple
from sqlalchemy import text
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
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

db_url_without_db, db_name = settings.database_url.rsplit("/", 1)
# 连接到 MySQL 服务器（不指定数据库）
engine_create = create_engine(db_url_without_db)

# 手动创建数据库（如果不存在）
with engine_create.connect() as connection:
    connection.execute(text(f"CREATE DATABASE IF NOT EXISTS {db_name};"))
    connection.commit()

# 连接到数据库
engine = create_engine(
    settings.database_url,
    pool_size=20,       # 连接池容量
    max_overflow=20,    # 溢出连接数量
    pool_timeout=60,    # 超时时间
    pool_recycle=1800,   # 避免数据库主动断开空闲连接
    pool_pre_ping=True,  # 自动检测连接是否存活
    echo=True,
    connect_args={
        "init_command": "SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ"
        # "init_command": "SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE"
    }
)
sessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
app.middleware("http")(log_requests)

@contextmanager
def session_scope():
    """提供一个独立的 session 上下文"""
    db = sessionLocal()
    try:
        db.begin()
        yield db
    finally:
        db.close()

def retryable(func):
    """
    只有当 func 返回 err_code == 0 时才提交事务
    否则回滚并抛出异常供 retry 捕获
    """
    @retry(
        stop=stop_after_attempt(60),                # 最多重试次数
        wait=wait_fixed(1),                         # 等待时间
        retry=retry_if_exception_type((DBAPIError, OperationalError, TimeoutError, InternalError)),     # 抛出这些异常后重试
        reraise=True                                # 所有重试失败后抛出原始异常
    )
    def wrapper(*args, **kwargs):
        with session_scope() as db:
            try:
                result = func(*args, db=db)
                # 判断是否操作成功
                if isinstance(result, dict) and result.get("err_code") == 0:
                    db.commit()
                else:
                    db.rollback()

                return result
            except Exception as e:
                db.rollback()
                raise  # 抛出异常供 tenacity 捕获以决定是否重试
    return wrapper



# def get_db():
#     db = sessionLocal()
#     #db.execute(text("SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
#     # 验证设置是否生效
#     # result = db.execute(text("SELECT @@session.transaction_isolation")).scalar()
#     # logger.info(f"当前隔离级别: {result}")  # 应输出 SERIALIZABLE
#     try:
#         yield db
#     finally:
#         db.close()

@app.on_event("startup")
def app_startup():
    logger.info("app startup!")
    model.Base.metadata.create_all(bind=engine)

    logger.info(f"Database URL: {settings.database_url}")
    logger.info(f"Max Svc ID: {settings.max_svc_id}")
    logger.info(f"Log to Console: {settings.log_to_console}")
    logger.info(f"Port: {settings.port}")


def alloc_new_ids(game_id: int, area_id: int, count: int, db: Session):
    """
        # 给某个版本(game_id)的游戏的区服分配id列表， 同一个 game_id 下的的 svc_id不能重复
    """

    # 锁定整个game_id区域
    db.execute(text(
        "SELECT 1 FROM svc_ids WHERE game_id = :game_id FOR UPDATE"
    ), {'game_id': game_id})


    new_ids = []  # 新申请id
    reuse_ids = []  # 重用id

    # 查询 svc_id 字段最大的记录
    # max_item = (db.query(SvcId).filter(SvcId.game_id == game_id, SvcId.delete_time == None)
    #             .order_by(SvcId.svc_id.desc()).with_for_update().first())
    # max_svc_id = max_item.svc_id if max_item else 0
    max_svc_id = (
                     db.query(func.max(SvcId.svc_id))
                     .filter(SvcId.game_id == game_id).with_for_update()
                     .scalar()  # 直接返回标量值
                 ) or 0  # 处理空值


    # 计算需要重复利用的id数量
    remain_id_count = max(0, settings.max_svc_id - max_svc_id)
    need_reuse_count = max(0, count - remain_id_count)
    if need_reuse_count <= 0:
        new_ids = [max_svc_id + i for i in range(1, count + 1)]
    else:
        # 查询 need_reuse_count 个已删除的svc_id
        reuse_list = db.query(SvcId).filter(SvcId.game_id == game_id, SvcId.delete_time != None
                                            ).order_by(SvcId.svc_id.asc()).limit(need_reuse_count).with_for_update().all()

        if len(reuse_list) < need_reuse_count:
            # raise Exception("数据库中可分配的进程实例id不足")
            return {"svc_ids": [], "err_code": 1, "err_msg": "数据库中可分配的进程实例id不足"}

        # 更新重用的svc_id
        reuse_ids = [item.svc_id for item in reuse_list]
        db.query(SvcId).filter(SvcId.game_id == game_id, SvcId.svc_id.in_(reuse_ids)).update(
            {"delete_time": None, "update_time": datetime.now(), "area_id": area_id},
            synchronize_session=False
        )

        for i in range(1, count - len(reuse_ids) + 1):
            new_ids.append(max_svc_id + i)


    # 写入新申请的svc_id
    db.bulk_insert_mappings(SvcId, [
        {"game_id": game_id, "area_id": area_id, "svc_id": id, "create_time": datetime.now(), "update_time": datetime.now()}
        for id in new_ids
    ])

    new_ids.extend(reuse_ids)
    # 从小到大排序
    new_ids.sort()
    return {"svc_ids": new_ids, "err_code": 0, "err_msg": ""}


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
    count: int          # 未查到会创建(数量等于0 不创建)

# 获取某个区服的所有进程实例id (如果有直接返回， 没有重新分配并返回)
@app.post("/svc_id/get")
def svc_id_get(req: SvcIdGet, db: Session = Depends(session_scope)):
    return do_svc_id_get(req, db = db)

@retryable
def do_svc_id_get(req: SvcIdGet, db: Session):
    # 查询数据库
    db_items = db.query(SvcId).filter(SvcId.game_id == req.game_id, SvcId.area_id == req.area_id, SvcId.delete_time == None).with_for_update().all()
    if len(db_items) > 0:
        return {"svc_ids": [item.svc_id for item in db_items], "err_code": 0, "err_msg": ""}

    if req.count == 0:
        return {"svc_ids": [], "err_code": 0, "err_msg": ""}
    else:
        # 申请进程id
        dic = alloc_new_ids(req.game_id, req.area_id, req.count, db)
        return dic


class SvcIdRecycle(BaseModel):
    game_id: int
    area_id: int

# 回收某个区服的所有进程实例id
@app.post("/svc_id/recycle")
def svc_id_recycle(req: SvcIdRecycle, db: Session = Depends(session_scope)):
    return do_svc_id_recycle(req, db = db)

@retryable
def do_svc_id_recycle(req: SvcIdRecycle, db: Session):
    # 锁定整个game_id区域
    db.execute(text(
        "SELECT 1 FROM svc_ids WHERE game_id = :game_id FOR UPDATE"
    ), {'game_id': req.game_id})

    # 批量更新操作（无需先查询）
    updated_count = (
        db.query(SvcId)
        .filter(
            SvcId.game_id == req.game_id,
            SvcId.area_id == req.area_id,
            SvcId.delete_time == None,
            )
        .update(
            {
                SvcId.delete_time: datetime.now(),
                SvcId.update_time: datetime.now(),
            },
            synchronize_session=False,  # 避免同步会话状态
        )
    )
    return {"err_code": 0, "err_msg": ""}

class SvcIdResize(BaseModel):
    game_id: int
    area_id: int
    resize: int

# 扩容或者缩容某个区服的进程实例id  返回操作后的实例id列表 (如果当前区服未分配进程id, 则不会进行任何操作)
@app.post("/svc_id/resize")
def svc_id_resize(req: SvcIdResize, db: Session = Depends(session_scope)):
    return do_svc_id_resize(req, db = db)

@retryable
def do_svc_id_resize(req: SvcIdResize, db: Session):
    # 锁定整个game_id区域
    db.execute(text(
        "SELECT 1 FROM svc_ids WHERE game_id = :game_id FOR UPDATE"
    ), {'game_id': req.game_id})


    # 查询数据库
    db_items = db.query(SvcId).filter(SvcId.game_id == req.game_id, SvcId.area_id == req.area_id, SvcId.delete_time == None).order_by(SvcId.svc_id.asc()).with_for_update().all()
    if len(db_items) == 0:
        return {"svc_ids": [], "err_code": 1, "err_msg": "当前区服未分配进程id，无法扩容或者缩容"}

    ids = [item.svc_id for item in db_items]
    if req.resize < 0 or len(db_items) == req.resize:
        return {"svc_ids": ids, "err_code": 0, "err_msg": ""}

    add_num = req.resize - len(db_items)
    if add_num > 0:
        # 扩容
        dic = alloc_new_ids(req.game_id, req.area_id, add_num, db)
        if dic["err_code"] != 0:
            return {"svc_ids": ids, "err_code": dic["err_code"], "err_msg": dic["err_msg"]}

        ids.extend(dic["svc_ids"])
        ids.sort()
    else:
        # 缩容
        delete_items = db_items[add_num:]
        for item in delete_items:
            ids.remove(item.svc_id)
            item.delete_time = datetime.now()
            item.update_time = datetime.now()

    return {"svc_ids": ids, "err_code": 0, "err_msg": ""}



if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.port  # 动态读取配置的端口
    )
