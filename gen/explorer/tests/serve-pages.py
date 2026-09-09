from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory


def main():
    source = Path(__file__).resolve().parents[1]
    output = source / "dist"
    if not (output / "index.html").is_file():
        raise SystemExit("Run npm run build before npm test")
    with TemporaryDirectory(prefix="easymesh-explorer-pages-") as temporary:
        root = Path(temporary)
        for prefix in ("", "meta-cmf-bananapi-vcpe", "another-project"):
            project = root / prefix
            project.mkdir(exist_ok=True)
            (project / "explorer").symlink_to(output, target_is_directory=True)
            (project / "index.html").symlink_to(source / "pages-index.html")
        handler = partial(SimpleHTTPRequestHandler, directory=str(root))
        with ThreadingHTTPServer(("127.0.0.1", 4178), handler) as server:
            server.serve_forever()


if __name__ == "__main__":
    main()
