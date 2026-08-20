from unittest.mock import Mock, call

from rec_console.recall_indexes import RecallIndexManager


def manager(indexes=None, active=None):
    client = Mock()
    client.indices.exists.return_value = False
    client.indices.exists_alias.return_value = bool(active)
    client.indices.get_alias.return_value = {index: {} for index in (active or [])}
    client.indices.get.return_value = {index: {} for index in (indexes or [])}
    client.count.return_value = {"count": 10}
    return RecallIndexManager(client)


def test_prepare_creates_staging_index_without_touching_alias():
    subject = manager()
    result = subject.prepare("i2i", "2026-08-20", "r002")
    assert result["index"] == "openrec-recall-i2i-20260820-r002"
    assert result["writable"] is True
    subject.client.indices.create.assert_called_once()
    subject.client.indices.update_aliases.assert_not_called()


def test_activate_validates_then_switches_and_keeps_two_versions():
    indexes = ["openrec-recall-hot-20260820-r001",
               "openrec-recall-hot-20260819-r001",
               "openrec-recall-hot-20260818-r001"]
    subject = manager(indexes, [indexes[1]])
    subject.client.indices.exists.return_value = True
    subject.client.count.return_value = {"count": 10}
    result = subject.activate("hot", indexes[0], 10, 2)
    assert result["previous_indexes"] == [indexes[1]]
    subject.client.indices.update_aliases.assert_called_once()
    assert subject.client.indices.delete.call_args_list == [call(index=indexes[2])]


def test_rollback_only_switches_alias_to_retained_index():
    indexes = ["openrec-recall-new-20260820-r001", "openrec-recall-new-20260819-r001"]
    subject = manager(indexes, [indexes[0]])
    result = subject.rollback("new")
    assert result["index"] == indexes[1]
    subject.client.indices.update_aliases.assert_called_once()
    subject.client.indices.delete.assert_not_called()


def test_list_indexes_allows_an_empty_release_history():
    subject = manager()
    result = subject.list_indexes("i2i")
    assert result == {"algorithm": "i2i", "active_indexes": [], "indexes": [],
                      "releases": []}
    subject.client.indices.get.assert_called_once_with(
        index="openrec-recall-i2i-*", allow_no_indices=True, ignore_unavailable=True
    )


def test_switch_moves_alias_without_deleting_an_index():
    indexes = ["openrec-recall-i2i-20260820-r001",
               "openrec-recall-i2i-20260819-r001"]
    subject = manager(indexes, [indexes[0]])
    result = subject.switch("i2i", indexes[1])
    assert result["index"] == indexes[1]
    subject.client.indices.update_aliases.assert_called_once()
    subject.client.indices.delete.assert_not_called()
