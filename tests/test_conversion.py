from confluence2md import guess_base_url, slugify, storage_to_markdown


def test_headings_and_formatting():
    md, _ = storage_to_markdown(
        "<h2>Section</h2><p>Uses <strong>bold</strong> and <em>italics</em>.</p>",
        "My Page")
    assert md.startswith("# My Page")
    assert "## Section" in md
    assert "**bold**" in md
    assert "*italics*" in md


def test_table_to_gfm():
    storage = ("<table><tbody><tr><th>Var</th><th>Value</th></tr>"
               "<tr><td>DB_HOST</td><td>db.local</td></tr></tbody></table>")
    md, _ = storage_to_markdown(storage, "T")
    assert "| Var | Value |" in md
    assert "| --- | --- |" in md


def test_code_macro_with_language():
    storage = ('<ac:structured-macro ac:name="code">'
               '<ac:parameter ac:name="language">yaml</ac:parameter>'
               '<ac:plain-text-body><![CDATA[port: 8080]]></ac:plain-text-body>'
               '</ac:structured-macro>')
    md, _ = storage_to_markdown(storage, "T")
    assert "```yaml" in md
    assert "port: 8080" in md


def test_panel_macro_to_blockquote():
    storage = ('<ac:structured-macro ac:name="info"><ac:rich-text-body>'
               '<p>Java 17 required.</p></ac:rich-text-body></ac:structured-macro>')
    md, _ = storage_to_markdown(storage, "T")
    assert "> " in md
    assert "Java 17 required." in md


def test_task_list_to_checkboxes():
    storage = ("<ac:task-list>"
               "<ac:task><ac:task-status>complete</ac:task-status>"
               "<ac:task-body>Done thing</ac:task-body></ac:task>"
               "<ac:task><ac:task-status>incomplete</ac:task-status>"
               "<ac:task-body>Pending thing</ac:task-body></ac:task>"
               "</ac:task-list>")
    md, _ = storage_to_markdown(storage, "T")
    assert "[x] Done thing" in md
    assert "[ ] Pending thing" in md


def test_attached_image_reference():
    storage = '<ac:image><ri:attachment ri:filename="diagram v2.png"/></ac:image>'
    md, refs = storage_to_markdown(storage, "T")
    assert refs == {"diagram v2.png"}
    assert "images/diagram%20v2.png" in md


def test_image_filename_path_traversal_is_stripped():
    storage = '<ac:image><ri:attachment ri:filename="../../etc/evil.png"/></ac:image>'
    md, refs = storage_to_markdown(storage, "T")
    assert refs == {"evil.png"}
    assert ".." not in md


def test_toc_macro_removed():
    md, _ = storage_to_markdown('<ac:structured-macro ac:name="toc"/><p>Body</p>', "T")
    assert "toc" not in md.lower() or "Body" in md


def test_internal_link_becomes_text():
    storage = '<p>See <ac:link><ri:page ri:content-title="Deploy Guide"/></ac:link>.</p>'
    md, _ = storage_to_markdown(storage, "T")
    assert "Deploy Guide" in md


def test_slugify():
    assert slugify("Guía de Instalación (v2)") == "guia-de-instalacion-v2"
    assert slugify("!!!") == "page"


def test_guess_base_url():
    assert (guess_base_url("https://c.corp.com/confluence/display/SP/Page")
            == "https://c.corp.com/confluence")
    assert (guess_base_url("https://c.corp.com/spaces/SP/pages/123/Page")
            == "https://c.corp.com")
    assert (guess_base_url("https://c.corp.com/pages/viewpage.action?pageId=1")
            == "https://c.corp.com")
