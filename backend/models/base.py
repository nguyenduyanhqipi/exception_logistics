from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


UUID_SERVER_DEFAULT = text("gen_random_uuid()")
