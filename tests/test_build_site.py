from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.build_site import BuildError, build_site


class StaticBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = TemporaryDirectory()
        self.root = Path(self.workspace.name) / "source"
        self.root.mkdir()
        self.output = Path(self.workspace.name) / "public"
        (self.root / "index.html").write_text("<h1>Landing page</h1>")
        preview = self.root / "previews/example.com/original/services"
        preview.mkdir(parents=True)
        (self.root / "previews/index.html").write_text("<h1>Preview directory</h1>")
        (preview / "index.html").write_text('<link rel="stylesheet" href="../site.css">')
        (preview.parent / "site.css").write_text("body { color: #123; }")

    def tearDown(self) -> None:
        self.workspace.cleanup()

    def test_only_curated_static_files_are_published_with_deep_paths(self) -> None:
        (self.root / ".env").write_text("SYNTHETIC_SECRET=not-real")
        reports = self.root / ".frictionless-reports"
        reports.mkdir()
        (reports / "private.html").write_text("Do not publish this report")
        self.assertEqual(build_site(self.root, self.output), 4)
        self.assertEqual(
            {p.relative_to(self.output).as_posix() for p in self.output.rglob("*") if p.is_file()},
            {
                "index.html", ".nojekyll", "previews/index.html",
                "previews/example.com/original/services/index.html",
                "previews/example.com/original/site.css",
            },
        )

    def test_private_or_unsupported_files_in_curated_output_fail_closed(self) -> None:
        for name in ("audit.json", "notes.md", ".env", "source.map"):
            with self.subTest(name=name):
                path = self.root / "previews" / name
                path.write_text("not a public asset")
                with self.assertRaises(BuildError):
                    build_site(self.root, self.output)
                self.assertFalse(self.output.exists())
                path.unlink()

    def test_symlink_to_private_content_is_rejected(self) -> None:
        private = self.root / "private.html"
        private.write_text("private source")
        (self.root / "previews/escape.html").symlink_to(private)
        with self.assertRaises(BuildError):
            build_site(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_output_and_source_paths_are_not_overwritten(self) -> None:
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("preserve")
        for destination in (self.output, self.root, self.root / "previews/build"):
            with self.subTest(destination=destination), self.assertRaises(BuildError):
                build_site(self.root, destination)
        self.assertEqual(sentinel.read_text(), "preserve")


if __name__ == "__main__":
    unittest.main()
