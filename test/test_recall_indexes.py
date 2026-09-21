from unittest.mock import Mock, call

import pytest

from rec_console.recall_indexes import RecallIndexManager


@pytest.fixture(autouse=True)
def release_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("REC_CONSOLE_DATA", str(tmp_path))


def manager(indexes=None, active=None, published=None):
    indexes = indexes or []
    active = active or []
    published = indexes if published is None else published
    client = Mock()
    aliases = {"active": list(active), "published": list(published)}
    metadata = {index: {"expected_documents": 10, "activated_at": index}
                for index in published}
    def names(alias):
        return aliases["published" if alias.endswith("-published") else "active"]
    client.indices.exists.return_value = False
    client.indices.exists_alias.side_effect = lambda name: bool(names(name))
    client.indices.get_alias.side_effect = lambda name: {index: {} for index in names(name)}
    client.indices.get.return_value = {index: {} for index in indexes}
    client.indices.get_mapping.side_effect = lambda index: {
        index: {"mappings": {"_meta": {"openrec_release": metadata.get(index, {})}}}}
    def put_mapping(index, body):
        metadata[index] = body["_meta"]["openrec_release"]
    client.indices.put_mapping.side_effect = put_mapping
    def update_aliases(actions):
        for action in actions:
            operation, change = next(iter(action.items()))
            entries = names(change["alias"])
            if operation == "remove" and change["index"] in entries:
                entries.remove(change["index"])
            elif operation == "add" and change["index"] not in entries:
                entries.append(change["index"])
    client.indices.update_aliases.side_effect = update_aliases
    client.count.return_value = {"count": 10}
    return RecallIndexManager(client)


def test_prepare_creates_staging_index_without_touching_alias():
    subject = manager()
    result = subject.prepare("content-i2i", "2026-08-20", "r002")
    assert result["index"] == "openrec-recall-content-i2i-20260820-r002"
    assert result["writable"] is True
    subject.client.indices.create.assert_called_once()
    subject.client.indices.update_aliases.assert_not_called()


def test_prepare_user_recall_creates_u2u_mapping():
    subject = manager()
    subject.prepare("user-als-emb", "2026-08-20", "r002")
    mapping = subject.client.indices.create.call_args.kwargs["mappings"]["properties"]
    assert set(mapping) == {"scene", "score", "left_user", "right_user"}


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
    result = subject.list_indexes("content-i2i")
    assert result == {"algorithm": "content-i2i", "active_indexes": [], "indexes": [],
                      "releases": []}
    subject.client.indices.get.assert_called_once_with(
        index="openrec-recall-content-i2i-*", allow_no_indices=True, ignore_unavailable=True
    )


def test_switch_moves_alias_without_deleting_an_index():
    indexes = ["openrec-recall-item-cf-i2i-20260820-r001",
               "openrec-recall-item-cf-i2i-20260819-r001"]
    subject = manager(indexes, [indexes[0]])
    result = subject.switch("item-cf-i2i", indexes[1])
    assert result["index"] == indexes[1]
    subject.client.indices.update_aliases.assert_called_once()
    subject.client.indices.delete.assert_not_called()


def test_rollback_skips_newer_staging_and_switch_rejects_it():
    old = "openrec-recall-hot-20260919-r001"
    active = "openrec-recall-hot-20260920-r001"
    staging = "openrec-recall-hot-20260921-r001"
    subject = manager([old, active, staging], [active], [old, active])
    assert subject.rollback("hot")["index"] == old
    with pytest.raises(ValueError, match="not retained"):
        subject.switch("hot", staging)
    with pytest.raises(ValueError, match="not retained"):
        subject.rollback("hot", staging)


def test_cleanup_preserves_previous_release_and_ignores_staging():
    previous = "openrec-recall-hot-20260918-r001"
    newer = "openrec-recall-hot-20260919-r001"
    active = "openrec-recall-hot-20260920-r001"
    staging = "openrec-recall-hot-20260921-r001"
    subject = manager([previous, newer, active, staging], [previous], [previous, newer])
    subject.client.indices.exists.return_value = True
    subject.activate("hot", active, 10, 2)
    assert subject.client.indices.delete.call_args_list == [call(index=newer)]


def test_prepare_does_not_overwrite_published_inactive_release():
    index = "openrec-recall-hot-20260919-r001"
    subject = manager([index], [], [index])
    subject.client.indices.exists.return_value = True
    assert subject.prepare("hot", "2026-09-19")["writable"] is False
    subject.client.indices.delete.assert_not_called()


def test_failed_alias_transaction_does_not_publish_staging():
    index = "openrec-recall-hot-20260919-r001"
    subject = manager([index], [], [])
    subject.client.indices.exists.return_value = True
    subject.client.indices.update_aliases.side_effect = RuntimeError("ES unavailable")
    with pytest.raises(RuntimeError):
        subject.activate("hot", index, 10)
    assert not subject.list_indexes("hot")["releases"][0]["published"]
    with pytest.raises(ValueError):
        subject.rollback("hot")


def test_rollback_revalidates_count_before_switch():
    index = "openrec-recall-hot-20260919-r001"
    subject = manager([index], [], [index])
    subject.client.count.return_value = {"count": 0}
    with pytest.raises(ValueError, match="expected 10"):
        subject.rollback("hot")
    subject.client.indices.update_aliases.assert_not_called()


def test_legacy_active_is_retained_only_after_validation():
    old = "openrec-recall-hot-20260918-r001"
    new = "openrec-recall-hot-20260919-r001"
    subject = manager([old, new], [old], [])
    subject.client.indices.exists.return_value = True
    subject.activate("hot", new, 10)
    assert subject.rollback("hot")["index"] == old
