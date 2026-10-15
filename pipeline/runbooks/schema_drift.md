# Schema drift (column renamed or retyped upstream)
Symptoms: Binder Error: Referenced column "X" not found in FROM clause. A staging model errors, downstream skipped.
Diagnose: compare columns of the raw table with the columns the staging model selects.
Fix: patch the staging model to read the new column name and alias it to the old name so downstream is unaffected.
Do NOT rename columns in the raw schema; it belongs to the ingestion team. Mention the drift to the owner afterwards.
