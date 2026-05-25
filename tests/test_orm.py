import logging
import sys
import psycopg2  # Importiamo il driver nativo per isolare il manager
from sqlalchemy import create_engine, Column, Integer, String, Numeric, event
from sqlalchemy.orm import declarative_base, sessionmaker
from pg_idx_manager.core import IndexManagerCore # Corretto l'import dal file core

DATABASE_URL = "postgresql+psycopg2://tester:supersecretpassword@localhost:5432/testing_perf"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

raw_dbapi_conn = psycopg2.connect("dbname=testing_perf user=tester password=supersecretpassword host=localhost port=5432")
manager = IndexManagerCore(raw_dbapi_conn, min_table_rows=0)

_ignoring_telemetry = False

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String)
    status = Column(String)
    amount = Column(Numeric)

@event.listens_for(engine, "before_cursor_execute")
def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executing_many):
    global _ignoring_telemetry
    
    if _ignoring_telemetry:
        return
        
    clean_statement = statement.strip().upper()
    if clean_statement.startswith("EXPLAIN") or "PG_CATALOG" in clean_statement:
        return

    try:
        _ignoring_telemetry = True
        
        anomalies, execution_time, io_stats = manager.analyze_query(statement, parameters)
        
        print("\n" + "="*50)
        print(f"   AUTOMATIC ORM QUERY TELEMETRY")
        print(f"   Execution Time: {execution_time} ms")
        print(f"   RAM Hit Blocks: {io_stats['hit']}")
        print(f"   Disk Read Blocks: {io_stats['read']}")
        print("="*50)
        print(f"   SQL: {statement.strip()}")
        if parameters:
            print(f"   Parameters: {parameters}")
        print("-"*50)
        
        if not anomalies:
            print(" Scan Type: INDEX SCAN (or Index-Only Scan)")
            print(" Status: Optimized execution.")
        else:
            print(" Scan Type: SEQUENTIAL SCAN (Full Table Scan)")
            for am in anomalies:
                print(f"   Target Table: '{am['table']}'")
                if am.get('filter'):
                    print(f"   Applied filter: {am['filter']}")
        print("="*50 + "\n")
        
    except Exception as e:
        try:
            raw_dbapi_conn.rollback()
        except:
            pass
        logging.warning(f"Could not audit ORM query safely: {e}")
    finally:
        _ignoring_telemetry = False

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    db_session = SessionLocal()
    
    try:
        print(" Running ORM queries... watch the console telemetry hooks!")
        
        print("\n[Executing ORM Query for customer_name...]")
        user_order = db_session.query(Order).filter(Order.customer_name == "pierpaolo").first()
        
        print("\n[Executing ORM Query for primary key ID...]")
        id_order = db_session.query(Order).filter(Order.id == 1).first()

        manager.save_to_csv()
        print("Telemetry saved to CSV cache file successfully.")

    finally:
        db_session.close()
        raw_dbapi_conn.close() 
