import psycopg2
import random
import string
# Importiamo solo il Core agnostico e la CLI dalla tua libreria pulita
from pg_index_manager import IndexManagerCore, run_cli

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
        
        # Check if data already exists to avoid duplication
        cursor.execute("SELECT COUNT(*) FROM orders;")
        if cursor.fetchone()[0] == 0:
            print("📦 Inserting 10,000 fake order records (this may take a few seconds)...")
            statuses = ['PENDING', 'COMPLETED', 'SHIPPED', 'CANCELLED']
            
            # Prepare bulk insert data
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
            print("✅ 10,000 rows inserted successfully.")
        else:
            print("✅ Database already populated.")


if __name__ == "__main__":
    # Connect to the local Docker Postgres instance
    connection_string = "dbname=testing_perf user=tester password=supersecretpassword host=localhost port=5432"
    
    try:
        conn = psycopg2.connect(connection_string)
        
        # 1. Setup the test database scenario
        setup_fake_data(conn)
        
        print("\n--- 🕵️ TESTING CORE AGNOSTIC ENGINE ---")
        # Instanziamo il motore a sé stante passando la connessione grezza
        manager = IndexManagerCore(conn, min_table_rows=0)
        
        # Testiamo una query non indicizzata per vedere se il motore estrae i millisecondi reali
        unindexed_query = "SELECT * FROM orders WHERE status = 'PENDING';"
        print(f"Analyzing query: {unindexed_query}")
        
        anomalies, execution_time = manager.analyze_query(unindexed_query)
        print(f"-> Analysis complete. Execution Time calculated by Postgres: {execution_time} ms")
        if anomalies:
            print(f"-> Engine detected a Sequential Scan on table: '{anomalies[0]['table']}'")

        print("\n--- 🖥️ LAUNCHING PERSISTENT INTERACTIVE CLI ---")
        # 2. Launch the interactive CLI to let you manage and clean up indexes manually
        run_cli(conn)

    except Exception as e:
        print(f"❌ Test script failed: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
