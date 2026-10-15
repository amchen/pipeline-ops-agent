# NULL foreign or primary keys
Symptoms: not_null test fails on customer_id or order_id.
Diagnose: count rows with NULL keys and check whether they share a time range or status.
Fix: as a temporary mitigation, exclude NULL-key rows in the staging model with a clear comment, then escalate to the
ingestion owner. Never fill NULLs with guessed values.
