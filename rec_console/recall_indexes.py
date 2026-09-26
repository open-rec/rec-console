"""Elasticsearch recall-index lifecycle management."""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from rec_console.release_lock import release_lock


RECALL_ALGORITHMS = ("hot", "new", "item-cf-i2i", "content-i2i", "user-cf-u2i",
                     "user-cf-u2u", "content-u2u", "user-als-emb", "sparse")
I2I_ALGORITHMS = ("item-cf-i2i", "content-i2i")
U2U_ALGORITHMS = ("user-cf-u2u", "content-u2u", "user-als-emb")


class RecallIndexManager:
    def __init__(self, client, prefix="openrec-recall", alias_suffix="active", data_root=None):
        self.client = client
        self.prefix = prefix
        self.alias_suffix = alias_suffix
        self.data_root = Path(data_root or os.environ.get("REC_CONSOLE_DATA", "/var/lib/rec-console"))

    def index_name(self, algorithm, business_date, revision="r001"):
        self._algorithm(algorithm)
        date_token = business_date.replace("-", "")
        if not re.match(r"^\d{8}$", date_token):
            raise ValueError("business_date must use YYYY-MM-DD")
        if not re.match(r"^r\d{3,}$", revision):
            raise ValueError("revision must look like r001")
        return "%s-%s-%s-%s" % (self.prefix, algorithm, date_token, revision)

    def alias_name(self, algorithm):
        self._algorithm(algorithm)
        return "%s-%s-%s" % (self.prefix, algorithm, self.alias_suffix)

    def prepare(self, algorithm, business_date, revision="r001"):
        self._algorithm(algorithm)
        with release_lock(self.data_root / "recall" / (self.alias_name(algorithm) + ".lock")):
            return self._prepare(algorithm, business_date, revision)

    def _prepare(self, algorithm, business_date, revision="r001"):
        index = self.index_name(algorithm, business_date, revision)
        alias = self.alias_name(algorithm)
        active = self._alias_indexes(alias)
        if self.client.indices.exists(index=index):
            if index in active or index in self._published(algorithm):
                return {"index": index, "alias": alias, "writable": False, "idempotent": True}
            self.client.indices.delete(index=index)
        self.client.indices.create(index=index, mappings=self._mapping(algorithm))
        return {"index": index, "alias": alias, "writable": True, "idempotent": False}

    def activate(self, algorithm, index, expected_documents, max_index_versions=2):
        self._algorithm(algorithm)
        with release_lock(self.data_root / "recall" / (self.alias_name(algorithm) + ".lock")):
            return self._activate(algorithm, index, expected_documents, max_index_versions)

    def _activate(self, algorithm, index, expected_documents, max_index_versions=2):
        self._validate_index(algorithm, index)
        if expected_documents <= 0:
            raise ValueError("expected_documents must be positive")
        if max_index_versions < 2:
            raise ValueError("max_index_versions must be at least 2 to support rollback")
        if not self.client.indices.exists(index=index):
            raise ValueError("recall index does not exist: %s" % index)
        actual = self._validate_documents(index, expected_documents)
        alias = self.alias_name(algorithm)
        previous = self._switch_alias(alias, index)
        deleted = self._cleanup(algorithm, index, max_index_versions, previous)
        return {"index": index, "alias": alias, "documents": actual,
                "previous_indexes": previous, "deleted_indexes": deleted}

    def rollback(self, algorithm, target_index=None):
        self._algorithm(algorithm)
        with release_lock(self.data_root / "recall" / (self.alias_name(algorithm) + ".lock")):
            return self._rollback(algorithm, target_index)

    def _rollback(self, algorithm, target_index=None):
        indexes = self._published(algorithm)
        alias = self.alias_name(algorithm)
        active = self._alias_indexes(alias)
        candidates = [index for index in indexes if index not in active]
        target = target_index or (candidates[0] if candidates else None)
        if target not in indexes:
            raise ValueError("rollback target is not retained: %s" % target)
        self._validate_release(target)
        previous = self._switch_alias(alias, target)
        return {"index": target, "alias": alias, "previous_indexes": previous}

    def switch(self, algorithm, target_index):
        self._algorithm(algorithm)
        with release_lock(self.data_root / "recall" / (self.alias_name(algorithm) + ".lock")):
            return self._switch(algorithm, target_index)

    def _switch(self, algorithm, target_index):
        self._validate_index(algorithm, target_index)
        indexes = self._published(algorithm)
        if target_index not in indexes:
            raise ValueError("switch target is not retained: %s" % target_index)
        alias = self.alias_name(algorithm)
        self._validate_release(target_index)
        previous = self._switch_alias(alias, target_index)
        return {"index": target_index, "alias": alias, "previous_indexes": previous}

    def list_indexes(self, algorithm):
        indexes = self._indexes(algorithm)
        active = self._alias_indexes(self.alias_name(algorithm))
        published = self._published(algorithm)
        releases = [{"index": index, "active": index in active, "published": index in published,
                     "documents": self.client.count(index=index)["count"]}
                    for index in indexes]
        return {"algorithm": algorithm, "active_indexes": active, "indexes": indexes,
                "releases": releases}

    def _switch_alias(self, alias, index):
        old_indexes = self._alias_indexes(alias)
        actions = [{"remove": {"index": old, "alias": alias}} for old in old_indexes]
        # The retained marker and serving alias change in the same ES transaction.
        # A validated staging index is not eligible until this transaction succeeds.
        for retained in set(old_indexes + [index]):
            metadata = self._release_metadata(retained)
            if not metadata:
                count = self.client.count(index=retained)["count"]
                self._validate_documents(retained, count)
            if retained == index:
                metadata = self._release_metadata(retained)
                metadata["activated_at"] = datetime.now(timezone.utc).isoformat()
                self.client.indices.put_mapping(index=retained, body={"_meta": {"openrec_release": metadata}})
            actions.append({"add": {"index": retained, "alias": alias + "-published"}})
        actions.append({"add": {"index": index, "alias": alias}})
        self.client.indices.update_aliases(actions=actions)
        return old_indexes

    def _cleanup(self, algorithm, active_index, maximum, previous):
        indexes = self._published(algorithm)
        retained = list(dict.fromkeys([active_index] + previous + indexes))[:maximum]
        deleted = []
        for index in indexes:
            if index not in retained:
                self.client.indices.delete(index=index)
                deleted.append(index)
        return deleted

    def _release_metadata(self, index):
        mapping = self.client.indices.get_mapping(index=index)[index]["mappings"]
        return dict(mapping.get("_meta", {}).get("openrec_release", {}))

    def _published(self, algorithm):
        indexes = self._alias_indexes(self.alias_name(algorithm) + "-published")
        return sorted(indexes, key=lambda index: (
            self._release_metadata(index).get("activated_at", ""), index), reverse=True)

    def _validate_documents(self, index, expected):
        if expected <= 0:
            raise ValueError("refusing to activate an empty recall index")
        # add_block waits for in-flight writes before validating the immutable release.
        self.client.indices.add_block(index=index, block="write")
        self.client.indices.refresh(index=index)
        actual = self.client.count(index=index)["count"]
        if actual != expected:
            raise ValueError("%s expected %d documents, got %d" % (index, expected, actual))
        metadata = self._release_metadata(index)
        metadata["expected_documents"] = expected
        self.client.indices.put_mapping(index=index, body={"_meta": {"openrec_release": metadata}})
        return actual

    def _validate_release(self, index):
        expected = self._release_metadata(index).get("expected_documents", 0)
        self._validate_documents(index, expected)

    def _indexes(self, algorithm):
        self._algorithm(algorithm)
        pattern = "%s-%s-*" % (self.prefix, algorithm)
        return sorted(self.client.indices.get(
            index=pattern, allow_no_indices=True, ignore_unavailable=True
        ).keys(), reverse=True)

    def _alias_indexes(self, alias):
        if not self.client.indices.exists_alias(name=alias):
            return []
        return list(self.client.indices.get_alias(name=alias).keys())

    def _validate_index(self, algorithm, index):
        self._algorithm(algorithm)
        if not re.match(r"^%s-%s-\d{8}-r\d{3,}$" %
                        (re.escape(self.prefix), re.escape(algorithm)), index or ""):
            raise ValueError("invalid %s recall index: %s" % (algorithm, index))

    @staticmethod
    def _algorithm(algorithm):
        if algorithm not in RECALL_ALGORITHMS:
            raise ValueError("unsupported recall serving table: %s" % algorithm)

    @staticmethod
    def _mapping(algorithm):
        if algorithm == "sparse":
            return {"properties": {
                "scene": {"type": "keyword"},
                "item": {"type": "keyword"},
                "text": {"type": "text", "similarity": "BM25"},
            }}
        properties = {"scene": {"type": "keyword"}, "score": {"type": "double"}}
        if algorithm in I2I_ALGORITHMS:
            properties.update({"left_item": {"type": "keyword"},
                               "right_item": {"type": "keyword"}})
        elif algorithm == "user-cf-u2i":
            properties.update({"user": {"type": "keyword"},
                               "item": {"type": "keyword"}})
        elif algorithm in U2U_ALGORITHMS:
            properties.update({"left_user": {"type": "keyword"},
                               "right_user": {"type": "keyword"}})
        else:
            properties["item"] = {"type": "keyword"}
            if algorithm == "new":
                properties["publish_time"] = {"type": "long"}
        return {"properties": properties}
