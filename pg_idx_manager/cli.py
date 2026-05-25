import sys
import re
from .core import IndexManagerCore

def is_safe_query(query: str) -> bool:
    clean_query = query.strip().upper()
    clean_query = re.sub(r'/\*.*?\*/', '', clean_query).strip()
    clean_query = re.sub(r'--.*$', '', clean_query, flags=re.M).strip()
    
    return clean_query.startswith(("SELECT", "WITH"))

def run_cli(connection):
    manager = IndexManagerCore(connection, min_table_rows=0)
    
    try:
        while True:
            print("\n" + "="*40)
            print("PERSISTENT PG INDEX MANAGER CLI")
            print("="*40)
            print("1. Audit single SQL query efficiency")
            print("2. Scan and clean up dead indexes (Janitor Mode)")
            print("Type 'quit' at any prompt to exit.")
            print("="*40)
            
            choice = input("\nSelect option (1/2 or 'quit'): ").strip().lower()
            
            if choice == "quit":
                manager.save_to_csv()
                print("\nExiting Index Manager. Keep your database clean!")
                break
                
            elif choice == "1":
                while True:
                    query = input("\nPaste SQL query to analyze (type 'back' for main menu, 'quit' to exit):\n> ").strip()
                    
                    if query.lower() == 'quit':
                        manager.save_to_csv()
                        print("\nExiting Index Manager. Keep your database clean!")
                        return
                    if query.lower() == 'back':
                        break
                    if not query:
                        continue
                    if not is_safe_query(query):
                        print("\nSECURITY ERROR: Only read-only SELECT/WITH queries are allowed for auditing.")
                        print("EXPLAIN ANALYZE executes data-modifying queries (INSERT/UPDATE/DELETE)! Blocked.")
                        continue
                    
                    try:
                        anomalies, execution_time, io_stats = manager.analyze_query(query)
                        
                        print("\n" + "="*40)
                        print(f"POSTGRESQL EXECUTION METRICS")
                        print(f"   Execution Time: {execution_time} ms")
                        print(f"   RAM Hit Blocks: {io_stats['hit']}")
                        print(f"   Disk Read Blocks: {io_stats['read']}")
                        print("="*40)
                        
                        if not anomalies:
                            print("   Scan Type: INDEX SCAN (or Index-Only Scan)")
                            print("   Status: The query is properly using database indexes.")
                            print("="*40)
                            continue
                            
                        print(" Scan Type: SEQUENTIAL SCAN (Full Table Scan)")
                        for am in anomalies:
                            print(f"   Target Table: '{am['table']}'")
                            
                            q_filter = am.get('filter')
                            if q_filter:
                                print(f"   Applied filter clause: {q_filter}")
                            else:
                                print("   Applied filter clause: [None - Entire table block read]")
                        print("="*40)
                                    
                    except Exception as e:
                        if not connection.autocommit:
                            connection.rollback()
                        print(f"\n SQL SYNTAX OR DATABASE ERROR: {e}")
                        print("Please verify your table names, column names, or SQL syntax.")
                        continue
                                
            elif choice == "2":
                print("\nScanning relational schemas for unused metadata indexes...")
                unused = manager.get_unused_indexes()
                if not unused:
                    print("Perfect! No dead indexes found in the database catalog.")
                    continue
                    
                print(f"Identified {len(unused)} unused indexes slowing down write operations:")
                for idx in unused:
                    # Visualizzazione corretta usando le chiavi del dizionario restituito dal core
                    print(f"\n- '{idx['index']}' on table '{idx['table']}' (Schema: '{idx['schema']}')")
                    confirm = input(f"  Drop index asynchronously (CONCURRENTLY)? [s/N]: ").lower().strip()
                    if confirm == 's':
                        try:
                            print(f"  Removing index metadata in background...")
                            manager.drop_index_safely(idx['index'], idx['schema'])
                            print(f"  Index '{idx['index']}' dropped successfully!")
                        except Exception as e:
                            print(f"  Runtime execution error: {e}")
                    else:
                        print("  Skipped.")
            else:
                print("\nInvalid choice. Please enter 1, 2, or 'quit'.")

    except KeyboardInterrupt:
        manager.save_to_csv()
        print("\n\n[Control+C] Interrupted by user. Exiting cleanly. Goodbye!")
        sys.exit(0)
