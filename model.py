from sqlalchemy import Column, Integer, String, create_engine, DateTime, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class SvcId(Base):
    __tablename__ = "svc_ids"

    id = Column(Integer, primary_key=True, autoincrement=True)  # 主键自增id
    game_id = Column(Integer, nullable=False, index=True)
    area_id = Column(Integer, nullable=False)
    svc_id = Column(Integer, nullable=False)
    create_time = Column(DateTime, nullable=False)
    update_time = Column(DateTime, nullable=False)
    delete_time = Column(DateTime, nullable=True, index=True)

    # 定义索引
    __table_args__ = (
        Index("game_id_area_id_svc_id", "game_id", "area_id", "svc_id"),  # 索引名、字段顺序
        Index("unique_game_area_svc_id", "game_id", "svc_id", unique=True),  # 索引名、字段顺序
    )

