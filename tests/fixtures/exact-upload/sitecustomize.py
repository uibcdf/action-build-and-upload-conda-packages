"""Fixture-only public metadata transport; reject every unexpected network read."""

import io
import os
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

if "OFFLINE_UPLOAD_ROOT" in os.environ:
    root = Path(os.environ["OFFLINE_UPLOAD_ROOT"])

    def offline_urlopen(url, *, timeout):
        assert url == "https://api.anaconda.org/release/uibcdf/example/1.2.3", url
        assert timeout == 20
        with (root / "reads").open("a") as stream:
            stream.write("public-read\n")
        registry = root / "registry.json"
        if not registry.exists():
            raise HTTPError(url, 404, "offline absent coordinate", {}, None)
        return io.BytesIO(registry.read_bytes())

    urllib.request.urlopen = offline_urlopen
