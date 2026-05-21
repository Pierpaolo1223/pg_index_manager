from sqlalchemy import create_engine, Column, Integer, String, Numeric
from sqlalchemy.orm import declarative_base, sessionmaker
from pg_index_manager.decorators import audit_index

# 1. Database Connection Configuration
DATABASE_URL = "postgresql+psycopg2://tester:supersecretpassword@localhost:5432/testing_perf"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. ORM Model Mapping
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String)
    status = Column(String)
    amount = Column(Numeric)

# 3. Intercepted Function
@audit_index(conn_param="raw_conn", min_rows=0)
def execute_backend_task(raw_conn, query):
    with raw_conn.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()

if __name__ == "__main__":
    db_session = SessionLocal()
    
    try:
        # Recuperiamo la connessione psycopg2 grezza in modo moderno
        raw_connection = db_session.connection()._dbapi_connection

        # Metti qui la tua query da testare
        orm_query = db_session.query(Order).filter(Order.customer_name == "pierpaolo")
        
        # Compile and bind parameters to get the raw SQL string
        sql_string = str(orm_query.statement.compile(engine, compile_kwargs={"literal_binds": True}))
        
        # Execute: the decorator handles the audit output automatically
        execute_backend_task(raw_conn=raw_connection, query=sql_string)

    finally:
        db_session.close()

