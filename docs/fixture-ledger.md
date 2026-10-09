# Hand-checkable fictional order ledger

All values below are integer USD cents. Only completed orders count. Discounts are line totals; posted refunds before 2026-03-01 are attributed to the order's original month. Source data is authored in `fixtures/sales.json`; no real customer or transaction data is used.

| North order | Month | Channel | Gross | Discounts | Posted refunds | Net |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| N-JAN-A | 2026-01 | direct | 400000 | 40000 | 60000 | 300000 |
| N-JAN-B | 2026-01 | direct | 350000 | 20000 | 30000 | 300000 |
| N-JAN-P | 2026-01 | partner | 450000 | 40000 | 10000 | 400000 |
| N-FEB-D | 2026-02 | direct | 500000 | 40000 | 80000 | 380000 |
| N-FEB-P | 2026-02 | partner | 600000 | 80000 | 120000 | 400000 |

January gross is 1200000, discounts 100000, refunds 100000: net 1000000. February gross is 1100000, discounts 120000, refunds 200000: net 780000. The change is -220000 cents / -22.0%. Direct contributes -220000 and partner contributes zero.

Each North order has two distinct lines; equal line amounts occur deliberately. Several orders have two refunds, and fulfillment has multiple events. Joining all child rows without pre-aggregation produces fanout. `SUM(DISTINCT)` would also lose legitimate equal-valued rows.

Two additional South orders and a synthetic private-customer table exercise exposure boundaries. They are excluded from a North snapshot. An explicit all-region request by a North analyst is denied before constructing any query snapshot. The full demo must record unchanged source-file fingerprints; unit tests independently compare them before and after execution.
