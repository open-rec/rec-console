"""Opt-in ES integration: use only a unique temporary recall namespace."""

import os
import uuid

import pytest
from elasticsearch import ApiError, Elasticsearch

from rec_console.recall_indexes import RecallIndexManager


@pytest.mark.skipif(not os.getenv("OPENREC_TEST_ES_URL"), reason="requires Elasticsearch")
def test_publication_rollback_and_retention_with_real_elasticsearch(tmp_path):
    client = Elasticsearch(
        os.environ["OPENREC_TEST_ES_URL"],
        basic_auth=(os.getenv("OPENREC_TEST_ES_USER", "elastic"),
                    os.getenv("OPENREC_TEST_ES_PASSWORD", "openrec-es-password")),
        verify_certs=False,
    )
    prefix = "openrec-audit-" + uuid.uuid4().hex
    manager = RecallIndexManager(client, prefix=prefix, data_root=tmp_path)
    created = []

    def prepare(day, write=True):
        index = manager.prepare("hot", "2026-09-%02d" % day)["index"]
        created.append(index)
        if write:
            client.index(index=index, id="one", document={"scene": "test", "item": "1", "score": 1.0})
        return index

    try:
        first = prepare(19)
        manager.activate("hot", first, 1)
        second = prepare(20)
        manager.activate("hot", second, 1)
        staging = prepare(21, write=False)
        assert manager.rollback("hot")["index"] == first
        with pytest.raises(ValueError, match="not retained"):
            manager.switch("hot", staging)
        assert manager.prepare("hot", "2026-09-20")["writable"] is False
        with pytest.raises(ApiError) as error:
            client.index(index=second, id="two", document={"item": "2"})
        assert error.value.status_code == 403
        newest = prepare(22)
        manager.activate("hot", newest, 1)
        assert client.indices.exists(index=first)
        assert client.indices.exists(index=staging)
        assert not client.indices.exists(index=second)
        assert manager.rollback("hot")["index"] == first
    finally:
        for index in created:
            client.indices.delete(index=index, ignore_unavailable=True)
        client.close()
