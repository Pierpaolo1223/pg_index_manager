import logging

class IndexManagerCore:
    """
    Core engine handling PostgreSQL index auditing and safe background cleanup.
    Does not require superuser privileges or invasive external extensions.
    """
    def __init__(self, connection, min_table_rows=1000):
        self.conn = connection
        self.min_table_rows = min_table_rows

    def _get_table_rows(self, cursor, table_name):
        """Queries PostgreSQL system catalogs to fetch live tuple statistics."""
        try:
            cursor.execute(
                "SELECT n_live_tup FROM pg_stat_user_tables WHERE relname = %s", 
                (table_name,)
            )
            res = cursor.fetchone()
            # res è una tupla tipo (10000,). Estraiamo il primo elemento res[0]
            return res[0] if res else 0
        except Exception:
            return 0


    def parse_explain_plan(self, node, anomalies=None):
        """Recursively traverses the EXPLAIN JSON tree to detect Sequential Scans."""
        if anomalies is None:
            anomalies = []

        if node.get("Node Type") == "Seq Scan":
            anomalies.append({
                "table": node.get("Relation Name"),
                "filter": node.get("Filter")
            })

        if "Plans" in node:
            for sub_node in node["Plans"]:
                self.parse_explain_plan(sub_node, anomalies)

        return anomalies

    def analyze_query(self, query):
        """
        Executes an EXPLAIN (ANALYZE, FORMAT JSON) on the target query.
        Safely unpacks the nested driver structure without bracket syntax bugs.
        """
        anomalies_detected = []
        with self.conn.cursor() as cursor:
            cursor.execute(f"EXPLAIN (ANALYZE, FORMAT JSON) {query}")
            raw_result = cursor.fetchone()
            
            # Step 1: Extract the list from the psycopg2 tuple
            if isinstance(raw_result, tuple) and len(raw_result) > 0:
                raw_result = raw_result[0]
            
            # Step 2: Extract the internal dictionary from the list
            if isinstance(raw_result, list) and len(raw_result) > 0:
                raw_result = raw_result[0]
                
            # Final validation: check if we successfully unpacked into a dictionary
            if not isinstance(raw_result, dict):
                raise ValueError("Failed to parse PostgreSQL JSON plan into a dictionary configuration.")
                
            plan = raw_result.get("Plan")
            execution_time_ms = raw_result.get("Execution Time", 0.0)
            
            if not plan:
                raise ValueError("The 'Plan' root node is missing from the database engine response.")
                
            raw_anomalies = self.parse_explain_plan(plan)
            
            for anomaly in raw_anomalies:
                table = anomaly["table"]
                rows = self._get_table_rows(cursor, table)
                
                if rows >= self.min_table_rows:
                    anomaly["table_rows"] = rows
                    anomaly["execution_time"] = execution_time_ms
                    anomalies_detected.append(anomaly)
                    
        return anomalies_detected, execution_time_ms



    def get_unused_indexes(self):
        """Scans pg_stat_user_indexes for dead indexes (idx_scan = 0)."""
        sql = """
            SELECT schemaname, relname AS table_name, indexrelname AS index_name
            FROM pg_stat_user_indexes
            JOIN pg_index ON pg_stat_user_indexes.indexrelid = pg_index.indexrelid
            WHERE idx_scan = 0 AND indisunique = FALSE
            ORDER BY relname ASC;
        """
        unused = []
        with self.conn.cursor() as cursor:
            cursor.execute(sql)
            for row in cursor.fetchall():
                unused.append({"schema": row[0], "table": row[1], "index": row[2]})
        return unused

    def drop_index_safely(self, index_name, schema="public"):
        """Drops an index asynchronously without acquiring exclusive locks."""
        sql = f"DROP INDEX CONCURRENTLY {schema}.{index_name};"
        with self.conn.cursor() as cursor:
            cursor.execute(sql)
            self.conn.commit()
