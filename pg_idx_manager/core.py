import logging
import csv
import os
import inspect
import re
from datetime import datetime

class IndexManagerCore:
    def __init__(self, connection, min_table_rows=0):
        self.conn = connection

    def parse_explain_plan(self, node, anomalies=None, stats=None):
        if anomalies is None:
            anomalies = []
        if stats is None:
            stats = {"hit": 0, "read": 0}

        stats["hit"] += node.get("Shared Hit Blocks", 0)
        stats["read"] += node.get("Shared Read Blocks", 0)

        if node.get("Node Type") == "Seq Scan":
            anomalies.append({
                "table": node.get("Relation Name"),
                "filter": node.get("Filter")
            })

        if "Plans" in node:
            for sub_node in node["Plans"]:
                self.parse_explain_plan(sub_node, anomalies, stats)

        return anomalies, stats

    def generate_query_fingerprint(self, query: str) -> str:
        sql = query.strip().lower()
        sql = re.sub(r'\s+', ' ', sql)
        sql = re.sub(r"'(?:''|[^'])*'", '?', sql)
        sql = re.sub(r'%\([^)]+\)s', '?', sql)
        sql = re.sub(r'%s', '?', sql)
        sql = re.sub(r'(?<!limit )\b\d+(?:\.\d+)?\b', '?', sql)
        return sql

    def log_to_csv(self, execution_time, scan_type, ram_hits, disk_reads, query):
        csv_file = "pg_query_audit.csv"
        current_fingerprint = self.generate_query_fingerprint(query)
        execution_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        calling_function = "unknown_context"
        stack = inspect.stack()
        for frame in stack:
            if "pg_idx_manager" not in frame.filename and "inspect" not in frame.filename:
                calling_function = frame.function
                break
        if calling_function == "<module>":
            calling_function = "main_script_execution"

        rows_to_keep = []
        query_updated = False

        if os.path.isfile(csv_file):
            with open(csv_file, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)
                
                for row in reader:
                    if row:
                        stored_sql = row[6]
                        stored_fingerprint = self.generate_query_fingerprint(stored_sql)
                        
                        if stored_fingerprint == current_fingerprint:
                            row[0] = execution_timestamp
                            row[1] = calling_function
                            row[2] = execution_time
                            row[3] = scan_type
                            row[4] = str(ram_hits)
                            row[5] = str(disk_reads)
                            row[6] = query.strip()
                            query_updated = True
                        
                        rows_to_keep.append(row)

        with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["execution_date", "calling_function", "execution_time_ms", "scan_type", "ram_hit_blocks", "disk_read_blocks", "raw_sql"])
            
            if rows_to_keep:
                writer.writerows(rows_to_keep)
                
            if not query_updated:
                writer.writerow([execution_timestamp, calling_function, execution_time, scan_type, ram_hits, disk_reads, query.strip()])

    def analyze_query(self, query, params=None):
        anomalies_detected = []
        with self.conn.cursor() as cursor:
            cursor.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}", params)
            raw_result = cursor.fetchone()
            
            if isinstance(raw_result, tuple) and len(raw_result) > 0:
                raw_result = raw_result[0]
            if isinstance(raw_result, list) and len(raw_result) > 0:
                raw_result = raw_result[0]
                
            if not isinstance(raw_result, dict):
                raise ValueError("Failed to parse PostgreSQL JSON plan.")
                
            plan = raw_result.get("Plan")
            execution_time_ms = raw_result.get("Execution Time", 0.0)
            
            if not plan:
                raise ValueError("The 'Plan' root node is missing.")
                
            raw_anomalies, io_stats = self.parse_explain_plan(plan)
            
            for anomaly in raw_anomalies:
                anomaly["execution_time"] = execution_time_ms
                anomalies_detected.append(anomaly)
            
            scan_type = "SEQUENTIAL SCAN" if anomalies_detected else "INDEX SCAN"
            
            ram_hits = io_stats["hit"]
            disk_reads = io_stats["read"]
            
            self.log_to_csv(execution_time_ms, scan_type, ram_hits, disk_reads, query)
                    
        return anomalies_detected, execution_time_ms, io_stats


    def get_unused_indexes(self):
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
        sql = f"DROP INDEX CONCURRENTLY {schema}.{index_name};"
        with self.conn.cursor() as cursor:
            cursor.execute(sql)
            self.conn.commit()
