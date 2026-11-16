"""Static checks on the web page. (Behaviour was checked in headless Chrome; see the step 7 report.)"""

import re
from pathlib import Path

PUBLIC = Path(__file__).resolve().parents[2] / "services" / "web" / "public"
APP_JS = (PUBLIC / "app.js").read_text()
# Comments are stripped so the security notes in app.js do not trip the checks.
APP_CODE = re.sub(r"^\s*//.*$", "", APP_JS, flags=re.MULTILINE)
INDEX = (PUBLIC / "index.html").read_text()

# Paths from contracts/api.md that the page is allowed to call.
CONTRACT_PATHS = {"/products", "/search", "/orders", "/login"}


def test_page_files_exist_and_are_linked():
    assert 'src="app.js"' in INDEX and 'href="style.css"' in INDEX
    assert (PUBLIC / "style.css").is_file()


def test_no_inline_script_or_handlers_so_a_strict_csp_works():
    assert re.search(r"<script(?![^>]*\bsrc=)", INDEX) is None
    assert re.search(r"\son[a-z]+=", INDEX) is None
    assert "<style" not in INDEX


def test_server_data_never_goes_through_innerHTML():
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert sink not in APP_CODE


def test_api_calls_go_through_edge_prefix_to_contract_paths():
    assert 'const API = "/api";' in APP_CODE
    # Every path literal, e.g. "/orders/" or "/search?q=", reduced to its first segment.
    literals = set(re.findall(r'"(/[a-z]+)(?:[/?][^"]*)?"', APP_CODE)) - {"/api"}
    assert literals == CONTRACT_PATHS


def test_token_not_persisted():
    assert "localStorage" not in APP_CODE and "sessionStorage" not in APP_CODE
    assert "document.cookie" not in APP_CODE
