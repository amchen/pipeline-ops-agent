# Negative amounts
Symptoms: assert_no_negative_amounts fails.
Diagnose: inspect the offending rows, their status, and whether they cluster in time. A sign-flip bug upstream is common.
Fix: do not silently abs() or delete values. Escalate with sample order_ids. A staging filter that quarantines negative
rows is acceptable only as a clearly commented temporary mitigation.
