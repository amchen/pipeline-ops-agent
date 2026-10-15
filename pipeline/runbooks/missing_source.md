# Missing source table
Symptoms: Catalog Error: Table with name X does not exist.
Diagnose: list tables in the raw schema and compare with sources.yml.
Fix: there is no safe fix in the pipeline. Never recreate or fabricate source tables.
Escalate to the ingestion owner immediately; this blocks all downstream models.
