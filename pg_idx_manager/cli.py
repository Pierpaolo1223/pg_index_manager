import sys
from .core import IndexManagerCore

def is_safe_query(query: str) -> bool:
    """Sanity check to ensure the tool only processes read-only SELECT queries."""
    clean_query = query.strip().upper()
    if len(clean_query) < 6:
        return True
    dangerous_keywords = ["DROP TABLE", "DROP DATABASE", "DELETE FROM", "INSERT INTO", "UPDATE ", "TRUNCATE "]
    for keyword in dangerous_keywords:
        if keyword in clean_query:
            return False
    return True

def run_cli(connection):
    """Launches a persistent, continuous loop for interactive DB optimization."""
    manager = IndexManagerCore(connection, min_table_rows=0)
    
    try:
        while True:
            print("\n" + "="*40)
            print("🚀 PERSISTENT PG INDEX MANAGER CLI")
            print("="*40)
            print("1. Audit single SQL query efficiency")
            print("2. Scan and clean up dead indexes (Janitor Mode)")
            print("Type 'quit' at any prompt to exit.")
            print("="*40)
            
            choice = input("\nSelect option (1/2 or 'quit'): ").strip().lower()
            
            if choice == "quit":
                print("\n👋 Exiting Index Manager. Keep your database clean!")
                break
                
            elif choice == "1":
                while True:
                    query = input("\nPaste SQL query to analyze (type 'back' for main menu, 'quit' to exit):\n> ").strip()
                    
                    if query.lower() == 'quit':
                        print("\n👋 Exiting Index Manager. Keep your database clean!")
                        return
                    if query.lower() == 'back':
                        break
                    if not query:
                        continue
                    if not is_safe_query(query):
                        print("\n❌ SECURITY ERROR: Only read-only SELECT queries are allowed for auditing.")
                        continue
                    
                    try:
                        # 🔑 FIX: Unpack the new third parameter containing I/O statistics
                        anomalies, execution_time, io_stats = manager.analyze_query(query)
                        
                        print("\n" + "="*40)
                        print(f"📊 POSTGRESQL EXECUTION METRICS")
                        print(f"   Execution Time: {execution_time} ms")
                        print(f"   RAM Hit Blocks: {io_stats['hit']}")
                        print(f"   Disk Read Blocks: {io_stats['read']}")
                        print("="*40)
                        
                        if not anomalies:
                            print(" 🎯 Scan Type: INDEX SCAN (or Index-Only Scan)")
                            print("   Status: The query is properly using database indexes.")
                            print("="*40)
                            continue
                            
                        print(" ℹ️  Scan Type: SEQUENTIAL SCAN (Full Table Scan)")
                        for am in anomalies:
                            print(f"   Target Table: '{am['table']}'")
                            
                            q_filter = am.get('filter')
                            if q_filter:
                                print(f"   Applied filter clause: {q_filter}")
                            else:
                                print("   Applied filter clause: [None - Entire table block read]")
                        print("="*40)
                                    
                    except Exception as e:
                        connection.rollback()
                        print(f"\n❌ SQL SYNTAX OR DATABASE ERROR: {e}")
                        print("Please verify your table names, column names, or SQL syntax.")
                        continue
                                
            elif choice == "2":
                print("\n🔎 Scanning relational schemas for unused metadata indexes...")
                unused = manager.get_unused_indexes()
                if not unused:
                    print("✅ Perfect! No dead indexes found in the database catalog.")
                    continue
                    
                print(f"ℹ️ Identified {len(unused)} unused indexes slowing down write operations:")
                for idx in unused:
                    print(f"- '{idx['index']}' on table '{idx['table']}'")
                    confirm = input(f"  Drop index asynchronously (CONCURRENTLY)? [s/N]: ").lower().strip()
                    if confirm == 's':
                        try:
                            print(f"  Removing index metadata in background...")
                            manager.drop_index_safely(idx['index'], idx['schema'])
                            print(f"  🚀 Index '{idx['index']}' dropped successfully!")
                        except Exception as e:
                            print(f"  ❌ Runtime execution error: {e}")
                    else:
                        print("  Skipped.")
            else:
                print("\n❌ Invalid choice. Please enter 1, 2, or 'quit'.")

    except KeyboardInterrupt:
        print("\n\n🛑 [Control+C] Interrupted by user. Exiting cleanly. Goodbye!")
        sys.exit(0)
