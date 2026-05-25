import logging
import csv
import os
import inspect
import re
from datetime import datetime

class IndexManagerCore:
    def __init__(self, connection, min_table_rows=0):
        self.conn = connection
        self.csv_file = "pg_query_audit.csv"
        self.queries_cache = {} 

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

    def log_to_cache(self, execution_time, scan_type, ram_hits, disk_reads, query):
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

        self.queries_cache[current_fingerprint] = [
            execution_timestamp, calling_function, current_fingerprint,
            execution_time, scan_type, ram_hits, disk_reads, query.strip()
        ]

    def save_to_csv(self):
        with open(self.csv_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "execution_date", 
                "calling_function", 
                "query_fingerprint", 
                "execution_time_ms", 
                "scan_type",         
                "ram_hit_blocks", 
                "disk_read_blocks", 
                "raw_sql"
            ])
            for row in self.queries_cache.values():
                writer.writerow(row)


    def analyze_query(self, query, params=None):
        anomalies_detected = []
        with self.conn.cursor() as cursor:
            try:
                cursor.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}", params)
                raw_result = cursor.fetchone()
            finally:
                if not self.conn.autocommit:
                    self.conn.rollback()
            
            if isinstance(raw_result, (tuple, list)) and len(raw_result) > 0:
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
            
            self.log_to_cache(execution_time_ms, scan_type, ram_hits, disk_reads, query)
                    
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
        original_autocommit = self.conn.autocommit
        try:
            self.conn.rollback() 
            self.conn.autocommit = True
            with self.conn.cursor() as cursor:
                cursor.execute(f'DROP INDEX CONCURRENTLY "{schema}"."{index_name}";')
        finally:
            self.conn.autocommit = original_autocommit
