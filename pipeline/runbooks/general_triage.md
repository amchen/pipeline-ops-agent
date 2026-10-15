# General triage for dbt build failures
Status `error` on a model means the SQL failed to run (binder/catalog error, missing column or table).
Status `fail` on a test means the data violates an expectation. Downstream nodes show `skipped`.
Steps: 1) read the log tail, 2) identify the first failing node, 3) inspect the raw table and the model SQL,
4) classify: schema_drift, data_quality, data_freshness, missing_source, model_logic.
Principles: prefer the smallest reversible fix in the dbt layer. Never modify or delete raw data without owner approval.
Anything you cannot fix inside the pipeline repo must be escalated with evidence.
