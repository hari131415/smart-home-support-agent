"""Device status lookups.

user_id always comes from the authenticated session, never from the model.
The tools below close over it, so the model can't ask about someone else's
devices even if a prompt tells it to.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class DeviceNotFound(LookupError):
    pass


class DeviceStore(Protocol):
    def list_devices(self, user_id: str) -> list[dict]: ...
    def get_device(self, user_id: str, device_id: str) -> dict: ...


class JsonDeviceStore:
    def __init__(self, path: str | Path):
        self._devices = json.loads(Path(path).read_text())["devices"]

    def list_devices(self, user_id: str) -> list[dict]:
        return [d for d in self._devices if d["user_id"] == user_id]

    def get_device(self, user_id: str, device_id: str) -> dict:
        for d in self.list_devices(user_id):
            if d["device_id"] == device_id:
                return d
        raise DeviceNotFound(device_id)


class BigQueryDeviceStore:
    """Reads the latest status snapshot, refreshed upstream every few minutes."""

    def __init__(self, project: str, table: str):
        from google.cloud import bigquery

        self._bq = bigquery
        self._client = bigquery.Client(project=project)
        self._table = table

    def _query(self, sql: str, **params) -> list[dict]:
        job_config = self._bq.QueryJobConfig(
            query_parameters=[
                self._bq.ScalarQueryParameter(k, "STRING", v) for k, v in params.items()
            ]
        )
        rows = self._client.query(sql, job_config=job_config).result()
        return [dict(r) for r in rows]

    def list_devices(self, user_id: str) -> list[dict]:
        return self._query(
            f"SELECT * FROM `{self._table}` WHERE user_id = @user_id ORDER BY name",
            user_id=user_id,
        )

    def get_device(self, user_id: str, device_id: str) -> dict:
        rows = self._query(
            f"SELECT * FROM `{self._table}` WHERE user_id = @user_id AND device_id = @device_id",
            user_id=user_id,
            device_id=device_id,
        )
        if not rows:
            raise DeviceNotFound(device_id)
        return rows[0]


def build_device_store(cfg) -> DeviceStore:
    d = cfg.devices
    if d["backend"] == "bigquery":
        project = cfg.gcp["project"]
        return BigQueryDeviceStore(project, f"{project}.{cfg.gcp['bq_dataset']}.{d['bq_table']}")
    return JsonDeviceStore(cfg.path(d["json_path"]))
