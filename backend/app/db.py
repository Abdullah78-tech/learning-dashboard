from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def create_database(url):
    options = {'check_same_thread': False, 'timeout': 15} if url.startswith('sqlite') else {}
    engine = create_engine(url, connect_args=options, pool_pre_ping=True)
    if url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def sqlite_foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
    return engine, sessionmaker(engine, expire_on_commit=False)


def get_db(request):
    with request.app.state.session_factory() as db:
        yield db
