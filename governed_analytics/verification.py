"""Runtime reference SQL for this catalog; never supplied as an actor tool."""

from .data import price_column

EXPRESSIONS = {"gross_sales_v1": "v.gross", "discounts_v1": "v.discount",
               "refunds_v1": "v.refund", "net_sales_v1": "v.gross - v.discount - v.refund"}


def reference_sql(metric, grouping, schema_version="sales_v1"):
    expression = EXPRESSIONS[metric]
    price = price_column(schema_version)
    groups = "SELECT 'direct' AS group_key UNION ALL SELECT 'partner'" if grouping == "channel" else "SELECT 'all' AS group_key"
    join_group = "AND v.channel = g.group_key" if grouping == "channel" else ""
    return f"""WITH values_per_order AS (
  SELECT o.order_date, o.channel,
    COALESCE((SELECT SUM(l.quantity * l.{price}) FROM order_lines l
              WHERE l.order_id = o.order_id), 0) AS gross,
    COALESCE((SELECT SUM(l.discount_cents) FROM order_lines l
              WHERE l.order_id = o.order_id), 0) AS discount,
    COALESCE((SELECT SUM(r.amount_cents) FROM refunds r WHERE r.order_id = o.order_id
              AND r.status = 'posted' AND r.posted_date < :as_of), 0) AS refund
  FROM orders o WHERE o.status = 'completed'
    AND substr(o.order_date, 1, 7) IN (:previous, :current)
), periods AS (
  SELECT DISTINCT period_key FROM period_coverage WHERE complete = 1 AND period_key IN (:previous, :current)
), groups AS ({groups})
SELECT p.period_key AS period_key, g.group_key AS group_key,
       COALESCE(SUM({expression}), 0) AS value_cents
FROM periods p CROSS JOIN groups g LEFT JOIN values_per_order v
ON substr(v.order_date, 1, 7) = p.period_key {join_group}
GROUP BY p.period_key, g.group_key ORDER BY p.period_key, g.group_key"""


def normalize(result):
    if not result.get("ok") or result.get("columns") != ["period_key", "group_key", "value_cents"]:
        raise ValueError("RESULT_SHAPE_MISMATCH")
    rows = result["rows"]
    keys = set()
    for row in rows:
        if len(row) != 3 or type(row[0]) is not str or type(row[1]) is not str or type(row[2]) is not int:
            raise ValueError("RESULT_SHAPE_MISMATCH")
        key = tuple(row[:2])
        if key in keys:
            raise ValueError("RESULT_SHAPE_MISMATCH")
        keys.add(key)
    return sorted(rows)


def compare(candidate, reference):
    try:
        actual = normalize(candidate)
        expected = normalize(reference)
    except ValueError as exc:
        return {"verified": False, "error": str(exc)}
    if actual != expected:
        return {"verified": False, "error": "GRAIN_OR_VALUE_MISMATCH"}
    return {"verified": True, "rows": actual}
