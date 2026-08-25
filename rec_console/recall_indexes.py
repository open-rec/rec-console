"""Elasticsearch recall-index lifecycle management."""

import re


RECALL_ALGORITHMS = ("hot", "new", "item-cf-i2i", "content-i2i", "user-cf-u2i")
I2I_ALGORITHMS = ("item-cf-i2i", "content-i2i")


class RecallIndexManager:
    def __init__(self, client, prefix="openrec-recall", alias_suffix="active"):
        self.client = client
        self.prefix = prefix
        self.alias_suffix = alias_suffix

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
        index = self.index_name(algorithm, business_date, revision)
        alias = self.alias_name(algorithm)
        active = self._alias_indexes(alias)
        if self.client.indices.exists(index=index):
            if index in active:
                return {"index": index, "alias": alias, "writable": False, "idempotent": True}
            self.client.indices.delete(index=index)
        self.client.indices.create(index=index, mappings=self._mapping(algorithm))
        return {"index": index, "alias": alias, "writable": True, "idempotent": False}

    def activate(self, algorithm, index, expected_documents, max_index_versions=2):
        self._validate_index(algorithm, index)
        if expected_documents <= 0:
            raise ValueError("expected_documents must be positive")
        if max_index_versions < 2:
            raise ValueError("max_index_versions must be at least 2 to support rollback")
        if not self.client.indices.exists(index=index):
            raise ValueError("recall index does not exist: %s" % index)
        self.client.indices.refresh(index=index)
        actual = self.client.count(index=index)["count"]
        if actual != expected_documents:
            raise ValueError("%s expected %d documents, got %d" %
                             (index, expected_documents, actual))
        alias = self.alias_name(algorithm)
        previous = self._switch_alias(alias, index)
        deleted = self._cleanup(algorithm, index, max_index_versions)
        return {"index": index, "alias": alias, "documents": actual,
                "previous_indexes": previous, "deleted_indexes": deleted}

    def rollback(self, algorithm, target_index=None):
        indexes = self._indexes(algorithm)
        alias = self.alias_name(algorithm)
        active = self._alias_indexes(alias)
        candidates = [index for index in indexes if index not in active]
        target = target_index or (candidates[0] if candidates else None)
        if target not in indexes:
            raise ValueError("rollback target is not retained: %s" % target)
        previous = self._switch_alias(alias, target)
        return {"index": target, "alias": alias, "previous_indexes": previous}

    def switch(self, algorithm, target_index):
        self._validate_index(algorithm, target_index)
        indexes = self._indexes(algorithm)
        if target_index not in indexes:
            raise ValueError("switch target is not retained: %s" % target_index)
        alias = self.alias_name(algorithm)
        previous = self._switch_alias(alias, target_index)
        return {"index": target_index, "alias": alias, "previous_indexes": previous}

    def list_indexes(self, algorithm):
        indexes = self._indexes(algorithm)
        active = self._alias_indexes(self.alias_name(algorithm))
        releases = [{"index": index, "active": index in active,
                     "documents": self.client.count(index=index)["count"]}
                    for index in indexes]
        return {"algorithm": algorithm, "active_indexes": active, "indexes": indexes,
                "releases": releases}

    def _switch_alias(self, alias, index):
        old_indexes = self._alias_indexes(alias)
        actions = [{"remove": {"index": old, "alias": alias}} for old in old_indexes]
        actions.append({"add": {"index": index, "alias": alias}})
        self.client.indices.update_aliases(actions=actions)
        return old_indexes

    def _cleanup(self, algorithm, active_index, maximum):
        indexes = self._indexes(algorithm)
        retained = [active_index]
        retained.extend([index for index in indexes if index != active_index][:maximum - 1])
        deleted = []
        for index in indexes:
            if index not in retained:
                self.client.indices.delete(index=index)
                deleted.append(index)
        return deleted

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
        properties = {"scene": {"type": "keyword"}, "score": {"type": "double"}}
        if algorithm in I2I_ALGORITHMS:
            properties.update({"left_item": {"type": "keyword"},
                               "right_item": {"type": "keyword"}})
        elif algorithm == "user-cf-u2i":
            properties.update({"user": {"type": "keyword"},
                               "item": {"type": "keyword"}})
        else:
            properties["item"] = {"type": "keyword"}
            if algorithm == "new":
                properties["publish_time"] = {"type": "long"}
        return {"properties": properties}
