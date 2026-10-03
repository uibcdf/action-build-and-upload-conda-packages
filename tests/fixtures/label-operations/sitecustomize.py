"""Intercept the installed client's HTTP transport; never contact a real registry."""

import json
import os
import sys
from pathlib import Path

if "OFFLINE_LABEL_ROOT" in os.environ:
    import requests

    root = Path(os.environ["OFFLINE_LABEL_ROOT"])

    def offline_request(session, method, url, **kwargs):
        assert sys.prefix == os.environ["OFFLINE_LABEL_PREFIX"]
        state = json.loads((root / "registry.json").read_text())
        record = state["distributions"][0]
        if method == "GET":
            assert url == "https://api.anaconda.org/release/uibcdf/example/1.2.3"
            assert "Authorization" not in session.headers
            result, status = state, 200
        else:
            assert session.headers["Authorization"] == "token offline-label-token"
            assert json.loads(kwargs["data"]) == {
                "package": "example",
                "version": "1.2.3",
                "basename": "noarch/example-1.2.3-py_0.conda",
            }
            if method == "POST":
                assert url == "https://api.anaconda.org/channels/uibcdf/withdrawn"
                if (root / "mode").read_text() != "archive_failure":
                    record["labels"].append("withdrawn")
            else:
                assert method == "DELETE"
                assert url == "https://api.anaconda.org/channels/uibcdf/main"
                assert "withdrawn" in record["labels"]
                record["labels"].remove("main")
            (root / "registry.json").write_text(json.dumps(state))
            result, status = {}, 201
        with (root / "calls.jsonl").open("a") as stream:
            stream.write(json.dumps({"method": method, "url": url}) + "\n")
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(result).encode()
        return response

    requests.Session.request = offline_request
