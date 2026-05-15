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
