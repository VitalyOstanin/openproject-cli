"""Tests for HAL payload normalization."""

from openproject_cli import normalize


def test_link_helpers():
    payload = {"_links": {"project": {"href": "/api/v3/projects/42", "title": "Sample Project"}}}
    assert normalize.link_title(payload, "project") == "Sample Project"
    assert normalize.link_id(payload, "project") == 42
    assert normalize.link_title(payload, "missing") is None
    assert normalize.link_id(payload, "missing") is None


def test_work_package():
    payload = {
        "id": 1234,
        "subject": "Sample task",
        "lockVersion": 3,
        "percentageDone": 50,
        "description": {"raw": "do it", "html": "<p>do it</p>"},
        "_links": {
            "type": {"title": "Task"},
            "status": {"title": "In progress"},
            "project": {"href": "/api/v3/projects/7", "title": "Sample Project"},
            "assignee": {"title": "Alice Example"},
        },
    }
    result = normalize.work_package(payload)
    assert result["id"] == 1234
    assert result["status"] == "In progress"
    assert result["project"] == "Sample Project"
    assert result["projectId"] == 7
    assert result["assignee"] == "Alice Example"
    assert result["description"] == "do it"
    assert result["lockVersion"] == 3


def test_time_entry():
    payload = {
        "id": 500,
        "hours": "PT5H",
        "spentOn": "2026-06-30",
        "comment": {"raw": "work"},
        "_links": {
            "user": {"href": "/api/v3/users/55", "title": "Alice Example"},
            "workPackage": {"href": "/api/v3/work_packages/1234", "title": "Sample task"},
            "activity": {"title": "Development"},
        },
    }
    result = normalize.time_entry(payload)
    assert result["hours"] == 5.0
    assert result["userId"] == 55
    assert result["workPackageId"] == 1234
    assert result["comment"] == "work"


def test_attachment_and_relation_and_comment():
    att = normalize.attachment(
        {
            "id": 9,
            "fileName": "r.pdf",
            "fileSize": 123,
            "_links": {"downloadLocation": {"href": "/x/9/content"}, "author": {"title": "A"}},
        }
    )
    assert att["fileName"] == "r.pdf"
    assert att["downloadUrl"] == "/x/9/content"

    rel = normalize.relation(
        {
            "id": 3,
            "type": "follows",
            "reverseType": "precedes",
            "_links": {"from": {"href": "/wp/1"}, "to": {"href": "/wp/2"}},
        }
    )
    assert rel["type"] == "follows"
    assert rel["from"] == 1
    assert rel["to"] == 2

    com = normalize.comment(
        {
            "id": 100,
            "_type": "Activity::Comment",
            "comment": {"raw": "hi"},
            "_links": {"user": {"title": "U"}},
        }
    )
    assert com["comment"] == "hi"
    assert com["user"] == "U"


def test_collection():
    payload = {"_embedded": {"elements": [{"id": 1}, {"id": 2}]}}
    assert normalize.collection(payload) == [{"id": 1}, {"id": 2}]
    assert normalize.collection({}) == []


def test_notification_projection():
    from openproject_cli import normalize

    payload = {
        "id": 5,
        "reason": "assigned",
        "readIAN": False,
        "createdAt": "2026-06-26T13:14:21Z",
        "_links": {
            "resource": {"href": "/openproject/work_packages/14344", "title": "Error"},
            "project": {"title": "Horizon"},
            "actor": {"href": "/openproject/api/v3/users/32", "title": "Jane Doe"},
            "activity": {"href": "/openproject/api/v3/activities/261301"},
        },
    }
    result = normalize.notification(payload)
    assert result == {
        "id": 5,
        "reason": "assigned",
        "read": False,
        "wpId": 14344,
        "wpTitle": "Error",
        "project": "Horizon",
        "actor": "Jane Doe",
        "activityHref": "/openproject/api/v3/activities/261301",
        "createdAt": "2026-06-26T13:14:21Z",
    }


def test_notification_read_flag_and_missing_links():
    from openproject_cli import normalize

    result = normalize.notification({"id": 1, "readIAN": True})
    assert result["read"] is True
    assert result["wpId"] is None
    assert result["wpTitle"] is None
    assert result["activityHref"] is None
