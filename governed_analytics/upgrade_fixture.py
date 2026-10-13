"""Host-only fictional fixture seam. No benchmark labels or arbitrary schema mappings."""
import json
import re
from dataclasses import dataclass
from datetime import date
from .data import TABLES, digest
from .upgrade_budget import UpgradeError
from .upgrade_gateway import strict_json

META = {"fictional", "fixture_id", "lineage", "source_version", "schema_version", "as_of", "currency"}


def validate_data(data):
    def reject():
        raise UpgradeError("INVALID_AUTHORED_FIXTURE")
    if type(data) is not dict or set(data) != META | set(TABLES):
        reject()
    if data["fictional"] is not True or data["currency"] != "USD":
        reject()
    for key in ("fixture_id", "lineage", "source_version"):
        if type(data[key]) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", data[key]):
            reject()
    if data["schema_version"] not in ("sales_v1", "sales_v2", "sales_future"):
        reject()
    try:
        if type(data["as_of"]) is not str or date.fromisoformat(data["as_of"]).isoformat() != data["as_of"]:
            reject()
    except ValueError:
        reject()
    for table, columns in TABLES.items():
        rows = data[table]
        if type(rows) is not list or len(rows) > 5000:
            reject()
        keys = set()
        for row in rows:
            if type(row) is not list or len(row) != len(columns):
                reject()
            if type(row[0]) is not str or (table == "period_coverage" and type(row[1]) is not str):
                reject()
            key = tuple(row[:2]) if table == "period_coverage" else row[0]
            if not isinstance(key, (str, tuple)) or key in keys:
                reject()
            keys.add(key)
            for column, value in zip(columns, row):
                if column in ("quantity", "unit_price_cents", "discount_cents", "amount_cents", "complete"):
                    if type(value) is not int or not 0 <= value <= 10**9:
                        reject()
                elif type(value) is not str or not value or len(value.encode("utf-8")) > 1024:
                    reject()
        if table == "orders":
            for row in rows:
                try:
                    if date.fromisoformat(row[1]).isoformat() != row[1]:
                        reject()
                except ValueError:
                    reject()
                if row[2] not in ("North", "South") or row[3] not in ("direct", "partner") or row[4] not in ("completed", "cancelled"):
                    reject()
        elif table == "refunds":
            for row in rows:
                try:
                    if date.fromisoformat(row[2]).isoformat() != row[2]:
                        reject()
                except ValueError:
                    reject()
                if row[4] not in ("posted", "pending", "void"):
                    reject()
        elif table == "order_lines" and any(row[2] == 0 for row in rows):
            reject()
        elif table == "period_coverage":
            if any(not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", row[0]) or row[1] not in ("North", "South") or row[2] not in (0, 1) for row in rows):
                reject()
    ids = {row[0] for row in data["orders"]}
    if any(row[1] not in ids for table in ("order_lines", "refunds", "fulfillment_events") for row in data[table]):
        reject()
    if len(json.dumps(data).encode("utf-8")) > 2000000:
        reject()
    return data


@dataclass(frozen=True)
class FixtureSnapshot:
    """Constructed only by the trusted caller; never accepted as provider arguments."""
    data_json: str

    def __post_init__(self):
        if type(self.data_json) is not str or len(self.data_json.encode("utf-8")) > 2000000:
            raise UpgradeError("INVALID_AUTHORED_FIXTURE")
        validate_data(strict_json(self.data_json))

    def payload(self):
        return validate_data(strict_json(self.data_json))

    def binding(self):
        return digest(self.payload())
