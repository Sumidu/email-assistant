from app.services import todos


def test_parse_todos_accepts_fenced_json_and_normalizes_fields():
    parsed = todos.parse_todos(
        """<think>ignore</think>
        ```json
        {"todos": [{"todo": "Reply to Ada", "due": "2026-05-16", "tags": "#email, followup"}]}
        ```
        """
    )

    assert parsed == [
        {
            "title": "Reply to Ada",
            "description": "",
            "due_date": "2026-05-16",
            "tags": ["email", "followup"],
            "location": "",
            "source_ids": [],
        }
    ]


def test_render_ics_escapes_task_fields():
    body = todos.render_ics([
        {
            "title": "Reply, then confirm",
            "description": "Line 1\nLine 2",
            "due_date": "2026-05-16",
            "tags": ["email", "followup"],
        }
    ])

    assert "BEGIN:VTODO" in body
    assert "SUMMARY:Reply\\, then confirm" in body
    assert "DESCRIPTION:Line 1\\nLine 2" in body
    assert "DUE;VALUE=DATE:20260516" in body

