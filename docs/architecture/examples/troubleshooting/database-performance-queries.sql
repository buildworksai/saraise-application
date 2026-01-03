-- ✅ APPROVED: Database Performance Monitoring Queries
-- Reference: docs/architecture/operational-runbooks.md § 3 (Performance Monitoring)
-- Also: docs/architecture/application-architecture.md § 4.1 (Row-Level Multitenancy)
-- 
-- CRITICAL: All queries in this file MUST include tenant_id filtering
-- No data leakage across tenant boundaries under any circumstances
-- Performance tuning MUST maintain Row-Level Multitenancy isolation

-- Check slow queries
SELECT query, mean_time, calls, total_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;

-- Check table sizes
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;

-- Check connection count
SELECT count(*) as connections, state
FROM pg_stat_activity
GROUP BY state;

