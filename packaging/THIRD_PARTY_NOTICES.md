# Distribution notices

Perish or Publish is copyright 2026 Munir Abbasi and distributed under the
PolyForm Noncommercial License 1.0.0. The full license accompanies the program.
This is a source-available noncommercial license, not an OSI-approved license.
The Publish or Perish concept is acknowledged without official affiliation.

Python, PySide6/Qt, Shiboken, Pydantic, HTTPX, BeautifulSoup, Typer, Rich,
Playwright, SQLite and their transitive dependencies retain their own licenses.
The native build collects installed distribution license and notice files under
`third-party-notices` and records exact installed versions. These files must
accompany redistribution. Chromium browser binaries are not included.

Qt/PySide6 are separately available under LGPLv3/GPLv3 or commercial terms.
Only Qt Core, Gui and Widgets are imported by the application. Shared Qt
libraries are kept separate in the directory bundle. Recipients must retain
their applicable rights to replace/relink those libraries and reverse engineer
for debugging changes to the LGPL components; this project's license must not
be interpreted to restrict those rights. An AppImage can be extracted with
`--appimage-extract` to access its directory bundle.

Before public redistribution, the release owner must review the actual bundled
Qt modules and third-party notices and supply the corresponding LGPL component
source (including any modifications), or a compliant source offer, together
with the applicable license texts and installation information. An upstream
link alone is not a claim that all distribution obligations have been met.

Authoritative references:

- https://doc.qt.io/qt-6/licensing.html
- https://doc.qt.io/qt-6/lgpl.html
- https://download.qt.io/official_releases/QtForPython/
- https://pyinstaller.org/en/stable/license.html

No signing or notarization is implied. Native artifacts remain unverified until
their respective startup smoke tests pass. Do not publish a draft release until
platform verification and redistribution review have been completed.
