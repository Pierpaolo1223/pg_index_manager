import psycopg2
import random
import string
from pg_idx_manager import IndexManagerCore, run_cli

def setup_fake_data(conn):
    """Creates a table and populates it with 10,000 rows to simulate production volume."""
    with conn.cursor() as cursor:
        print("🛠️ Setting up database table and fake data...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                customer_name TEXT,
                status TEXT,
                amount NUMERIC
            );
        """)
        
        cursor.execute("SELECT COUNT(*) FROM orders;")
        if cursor.fetchone()[0] == 0:
            print("Inserting 10,000 fake order records (this may take a few seconds)...")
            statuses = ['PENDING', 'COMPLETED', 'SHIPPED', 'CANCELLED']
            
            bulk_data = []
            for _ in range(10000):
                name = ''.join(random.choices(string.ascii_uppercase, k=8))
                status = random.choice(statuses)
                amount = round(random.uniform(10.0, 500.0), 2)
                bulk_data.append((name, status, amount))
                
            cursor.executemany(
                "INSERT INTO orders (customer_name, status, amount) VALUES (%s, %s, %s);", 
                bulk_data
            )
            conn.commit()
            print("10,000 rows inserted successfully.")
        else:
            print("Database already populated.")


if __name__ == "__main__":
    connection_string = "dbname=testing_perf user=tester password=supersecretpassword host=localhost port=5432"
    
    try:
        conn = psycopg2.connect(connection_string)
        
        setup_fake_data(conn)
        
        print("\n--- TESTING CORE AGNOSTIC ENGINE ---")
        manager = IndexManagerCore(conn, min_table_rows=0)
        
        unindexed_query = "SELECT * FROM orders WHERE status = 'PENDING';"
        print(f"Analyzing query: {unindexed_query}")
        
        anomalies, execution_time, io_stats = manager.analyze_query(unindexed_query)
        
        print(f"-> Analysis complete. Metrics calculated by Postgres:")
        print(f"   Execution Time: {execution_time} ms")
        print(f"   RAM Hit Blocks: {io_stats['hit']}")
        print(f"   Disk Read Blocks: {io_stats['read']}")
        
        if anomalies:
            print(f"-> Engine detected a Sequential Scan on table: '{anomalies[0]['table']}'")

        print("\n--- LAUNCHING PERSISTENT INTERACTIVE CLI ---")
        
        conn.rollback()
        
        conn.autocommit = True
        
        run_cli(conn)

    except Exception as e:
        print(f"Test script failed: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
