import unittest
from unittest.mock import patch

from scripts.promote_conda_package import (
    _public_api,
    parse_exact_spec,
    promote_exact_package,
)


class FakeAPI:
    def __init__(self, labels):
        self.labels = labels
        self.added = []

    def release(self, owner, package, version):
        distributions = []
        for label, files in self.labels.items():
            for item in files:
                existing = next(
                    (entry for entry in distributions if entry["full_name"] == item["full_name"]),
                    None,
                )
                if existing is None:
                    existing = {**item, "labels": []}
                    distributions.append(existing)
                existing["labels"].append(label)
        return {"distributions": distributions}

    def add_channel(self, channel, owner, package=None, version=None, filename=None):
        self.added.append((channel, owner, package, version, filename))
        full_name = f"{owner}/{package}/{version}/{filename}"
        source = next(
            item
            for files in self.labels.values()
            for item in files
            if item["full_name"] == full_name
        )
        self.labels.setdefault(channel, []).append(dict(source))


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.package = parse_exact_spec(
            "uibcdf/example/1.2.3/noarch/example-1.2.3-py_0.conda"
        )
        self.digest = "a" * 64
        self.file = {
            "full_name": self.package.full_name,
            "sha256": self.digest,
        }

    def test_promotes_one_exact_digest_and_verifies_the_target(self):
        api = FakeAPI({"staging": [self.file], "main": []})

        receipt = promote_exact_package(
            api,
            package=self.package,
            source_label="staging",
            target_label="main",
            expected_sha256=self.digest,
        )

        self.assertEqual(receipt["status"], "verified")
        self.assertEqual(receipt["package"], self.package.full_name)
        self.assertEqual(
            api.added,
            [
                (
                    "main",
                    "uibcdf",
                    "example",
                    "1.2.3",
                    "noarch/example-1.2.3-py_0.conda",
                )
            ],
        )

    def test_uses_the_token_client_only_for_the_label_write(self):
        read_api = FakeAPI({"staging": [self.file], "main": []})

        class WriteOnlyAPI:
            def add_channel(inner, *args, **kwargs):
                read_api.add_channel(*args, **kwargs)

            def release(inner, *args, **kwargs):
                raise AssertionError(
                    "authenticated client must not perform public reads"
                )

        receipt = promote_exact_package(
            read_api,
            write_api=WriteOnlyAPI(),
            package=self.package,
            source_label="staging",
            target_label="main",
            expected_sha256=self.digest,
        )

        self.assertEqual(receipt["status"], "verified")

    def test_public_api_discards_an_ambient_write_only_token(self):
        def discover_ambient_token(*, cls):
            return cls("upload-only-token", domain="https://api.anaconda.org")

        with patch(
            "scripts.promote_conda_package.get_server_api",
            side_effect=discover_ambient_token,
        ):
            client = _public_api()

        self.assertIsNone(client.token)
        self.assertNotIn("Authorization", client.session.headers)

    def test_is_idempotent_when_the_exact_target_is_already_present(self):
        api = FakeAPI({"staging": [self.file], "main": [self.file]})

        promote_exact_package(
            api,
            package=self.package,
            source_label="staging",
            target_label="main",
            expected_sha256=self.digest,
        )

        self.assertEqual(api.added, [])

    def test_rejects_absent_source_digest_mismatch_and_broad_specs(self):
        with self.assertRaisesRegex(RuntimeError, "absent from source"):
            promote_exact_package(
                FakeAPI({"staging": [], "main": []}),
                package=self.package,
                source_label="staging",
                target_label="main",
                expected_sha256=self.digest,
            )
        with self.assertRaisesRegex(RuntimeError, "source digest mismatch"):
            promote_exact_package(
                FakeAPI(
                    {
                        "staging": [
                            {"full_name": self.package.full_name, "sha256": "b" * 64}
                        ],
                        "main": [],
                    }
                ),
                package=self.package,
                source_label="staging",
                target_label="main",
                expected_sha256=self.digest,
            )
        for value in (
            "uibcdf/example/1.2.3",
            "uibcdf/example/1.2.3/noarch",
            "uibcdf/example/1.2.3/noarch/not-a-package.txt",
            "uibcdf/example/1.2.3/noarch/nested/example-1.2.3-py_0.conda",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_exact_spec(value)

    def test_rejects_target_that_does_not_materialize(self):
        class NoOpAPI(FakeAPI):
            def add_channel(self, *args, **kwargs):
                pass

        with self.assertRaisesRegex(RuntimeError, "promotion returned"):
            promote_exact_package(
                NoOpAPI({"staging": [self.file], "main": []}),
                package=self.package,
                source_label="staging",
                target_label="main",
                expected_sha256=self.digest,
            )


if __name__ == "__main__":
    unittest.main()
