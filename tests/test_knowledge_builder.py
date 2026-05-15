from modules.knowledge_builder import KnowledgeBuilder


def test_split_frontmatter_parses_lists_and_body():
    frontmatter, body = KnowledgeBuilder._split_frontmatter(
        "---\n"
        'title: "Ada Lovelace"\n'
        'aliases: ["ada@example.com", "a.lovelace@example.com"]\n'
        "source: contact_profile\n"
        "---\n\n"
        "# Notes\nBody"
    )

    assert frontmatter["title"] == "Ada Lovelace"
    assert frontmatter["aliases"] == ["ada@example.com", "a.lovelace@example.com"]
    assert frontmatter["source"] == "contact_profile"
    assert body == "# Notes\nBody"


def test_normalize_aliases_keeps_only_email_like_values():
    aliases = KnowledgeBuilder._normalize_aliases("Ada, ada@example.com, ADA@example.com, other@example.com")

    assert aliases == ["ada@example.com", "other@example.com"]


def test_pattern_matches_address_supports_domains_and_wildcards():
    assert KnowledgeBuilder._pattern_matches_address("*.example.com", "person@mail.example.com")
    assert KnowledgeBuilder._pattern_matches_address("*@example.com", "person@example.com")
    assert not KnowledgeBuilder._pattern_matches_address("example.org", "person@example.com")


def test_frontmatter_round_trip_preserves_metadata_and_body():
    builder = object.__new__(KnowledgeBuilder)

    rendered = builder._compose_markdown(
        "ada_example.com.md",
        "# Ada\nNotes",
        {
            "source": "contact_profile",
            "aliases": ["ada@example.com"],
            "match_patterns": ["*@example.com"],
            "llm_id": "local",
            "llm_name": "Local",
            "model": "model",
            "generated_at": "2026-05-15T10:00:00",
        },
    )
    frontmatter, body = builder._split_frontmatter(rendered)

    assert frontmatter["type"] == "contact"
    assert frontmatter["email"] == "ada@example.com"
    assert frontmatter["aliases"] == ["ada@example.com"]
    assert body == "# Ada\nNotes"


def test_knowledge_category_splits_people_and_other():
    assert KnowledgeBuilder._knowledge_category("ada_example.com.md", {"source": "contact_profile"}) == "People"
    assert KnowledgeBuilder._knowledge_category("_writing_style.md", {}) == "Other"
