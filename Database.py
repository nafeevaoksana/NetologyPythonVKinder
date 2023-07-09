from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped, Session

from config import DB_URL_OBJECT


class Base(DeclarativeBase):
    pass


class ViewedProfile(Base):
    __tablename__ = 'viewed_profile'

    user_id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(primary_key=True)


class Database:

    def __init__(self, connection_string):
        self.engine = create_engine(connection_string, echo=True)

    def create_db(self):
        Base.metadata.create_all(self.engine)

    def insert_viewed_profile(self, user_id, profile_id):
        with Session(self.engine) as session:
            profile = ViewedProfile(user_id=user_id, profile_id=profile_id)
            session.add(profile)
            session.commit()

    def is_profile_viewed(self, user_id, profile_id):
        with Session(self.engine) as session:
            query = session \
                .query(ViewedProfile) \
                .filter_by(user_id=user_id, profile_id=profile_id) \
                .exists()
            return session.query(query).scalar()


if __name__ == '__main__':
    database = Database(DB_URL_OBJECT)
    database.create_db()
