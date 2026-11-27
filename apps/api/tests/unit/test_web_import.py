"""Website snapshot tool: page selection and text extraction. FAKE HTML only, no network."""

import pytest

from app.devtools.web_import import category_for, clean_title, extract, select_urls

HTML = """<html><head><title>Fee Structure EN_DASH Test University</title>
<style>.x{color:red}</style></head>
<body>
<nav>Home | Admissions | Login</nav>
<main id="main">
 <div class="post-content">
  <span class="rich-snippet-hidden">Fee StructureAdmin2026-09-30T10:00:00+00:00</span>
  <h2>Fee Structure (FY 2026-27)</h2>
  <script>var tracking = 1;</script>
  <p>Programs: BS Test</p>
  <table>
   <tr><th>Head</th><th>Amount</th></tr>
   <tr><td>Admission Fee</td><td> 1,000 </td></tr>
   <tr><td>Tuition Fee (Per Credit Hour)</td><td>2,000</td></tr>
  </table>
  <p>Programs: BS Test</p>
 </div>
</main>
<footer>Copyright Test University</footer>
</body></html>""".replace("EN_DASH", chr(0x2013))


def test_extract_keeps_main_content_and_tables_only() -> None:
    title, content, modified = extract(HTML)
    assert clean_title(title, "TU") == "Fee Structure"
    assert modified == "2026-09-30"
    lines = content.splitlines()
    assert lines[0] == "Fee Structure (FY 2026-27)"
    assert "Head | Amount" in lines
    assert "Admission Fee | 1,000" in lines
    assert "Tuition Fee (Per Credit Hour) | 2,000" in lines
    for noise in ("Login", "tracking", "color:red", "Copyright", "2026-09-30T"):
        assert noise not in content


def test_page_without_main_gives_no_content() -> None:
    assert extract("<html><body><p>menu only</p></body></html>")[1] == ""


def test_select_urls_uses_allowlist_and_student_topics() -> None:
    urls = [
        "https://test.edu/fee-structure/",
        "https://test.edu/admission-criteria/",
        "https://test.edu/login/",
        "https://test.edu/qec-team/",
        "https://test.edu/news-events/",
        "https://evil.example/fee-structure/",
        "https://test.edu/fee-structure/",
    ]
    assert select_urls(urls, ["test.edu"]) == [
        "https://test.edu/admission-criteria/",
        "https://test.edu/fee-structure/",
    ]


@pytest.mark.parametrize(
    ("path", "category"),
    [("/bs-se-fee-structure/", "fees"), ("/admission-test-guidelines/", "admissions"),
     ("/scholarships/", "scholarships"), ("/student-handbook/", "policies"),
     ("/exams/", "exams"), ("/contact/", "contacts"), ("/bs-cs-road-map/", "programs")],
)  # fmt: skip
def test_category_for(path: str, category: str) -> None:
    assert category_for(path) == category
