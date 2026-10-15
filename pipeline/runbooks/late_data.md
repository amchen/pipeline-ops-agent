# Late or missing recent data (freshness failure)
Symptoms: the freshness test fails; max(order_ts) is older than the reference time.
Diagnose: compare max(order_ts) in the raw table with raw.pipeline_meta.as_of and count rows per day.
Fix: there is NO fix inside this pipeline. Do not backfill, fabricate rows, or edit the reference time.
Escalate to the data-platform owner with the last loaded timestamp and the per-day row counts.
