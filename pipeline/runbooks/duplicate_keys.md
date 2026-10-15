# Duplicate primary keys
Symptoms: unique test fails on a staging key (for example order_id).
Diagnose: select key, count(*) from the raw table group by key having count(*) > 1.
Fix: deduplicate in the staging model with row_number() over (partition by key order by order_ts) and keep the first row.
Do not DELETE from raw tables. Notify the ingestion owner so the duplicate source can be fixed.
