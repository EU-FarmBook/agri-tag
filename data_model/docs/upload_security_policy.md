# Upload Security Policy

## Purpose

This document defines which uploaded or linked file types should be blocked for security reasons, independently of the KO taxonomy.

The key principle is:

- the platform should not accept files or direct links that primarily deliver executable code, installers, or scriptable payloads

The risk is not only the extension itself, but whether the asset:

- executes code,
- installs software,
- modifies the operating system,
- or is commonly used to deliver executable or script-based payloads.

---

## Core Rule

The platform should block:

1. uploaded executable or installable payloads
2. uploaded script files intended for execution
3. uploaded archives when archive inspection reveals blocked payloads inside
4. URL-based KOs that point directly to executable, installable, or script payloads

The platform may still allow:

- documentation about software
- repository URLs
- product landing pages
- software homepages
- curated source-code archives only if that is explicitly approved in a separate workflow

---

## Security Position For `Software Application`

`Software Application` may remain a valid taxonomy category for `URL-based KOs`, but this does **not** mean that the platform should allow direct software binaries or direct binary download URLs.

Allowed examples:

- software landing page
- product page
- app homepage
- documentation page
- source repository page

Not allowed:

- direct `.exe`, `.msi`, `.pkg`, `.dmg`, `.deb`, `.rpm`, `.AppImage`, `.sh`, `.run`, or similar payload links

So the operational rule is:

- `Software Application` is taxonomy-valid for URL-based KOs
- direct executable delivery is not allowed in either file-based or URL-based flows

---

## Blocked High-Risk File Extensions

### 1. Windows

Block:

- `.exe`
- `.msi`
- `.msp`
- `.bat`
- `.cmd`
- `.com`
- `.scr`
- `.ps1`
- `.psm1`
- `.vbs`
- `.vb`
- `.js`
- `.jse`
- `.wsf`
- `.wsh`
- `.dll`

### 2. macOS

Block:

- `.app`
- `.pkg`
- `.mpkg`
- `.dmg`
- `.command`
- `.workflow`
- `.scpt`
- `.applescript`
- `.kext`

### 3. Linux and Unix-like Systems

Block:

- `.deb`
- `.rpm`
- `.AppImage`
- `.sh`
- `.bash`
- `.zsh`
- `.run`
- `.bin`
- `.so`

### 4. Cross-platform Executable or Scriptable Payloads

Block:

- `.jar`
- `.py`
- `.pyc`
- `.pyo`
- `.php`
- `.pl`
- `.rb`
- `.cgi`

### 5. Container and Archive Formats Requiring Inspection

These are not always blocked by extension alone, but they must be inspected and rejected if they contain blocked payloads:

- `.zip`
- `.7z`
- `.rar`
- `.tar`
- `.tar.gz`
- `.tgz`
- `.tar.xz`
- `.gz`
- `.bz2`
- `.xz`

Default rule:

- if archive inspection is not implemented, these formats should be treated conservatively
- if archive inspection is implemented, reject archives containing blocked executable or script files

---

## URL-based KO Rule

For `URL-based KOs`, the system should reject direct links to the blocked executable or installable types above.

Examples that should be rejected:

- direct `.exe` download URLs
- direct `.msi` download URLs
- direct `.pkg` or `.dmg` URLs
- direct `.deb`, `.rpm`, `.AppImage`, `.sh`, or `.run` URLs
- archive URLs whose filenames clearly indicate binary installers and are not part of an approved curated workflow

Examples that may be accepted:

- software homepages
- documentation URLs
- GitHub or GitLab repository pages
- release pages that are not treated as direct binary uploads by the KO flow

---

## Validation Layers

Extension filtering alone is not sufficient.

The upload pipeline should use layered validation:

1. extension deny-list
2. MIME / content-type validation
3. magic-byte or file-signature validation where possible
4. archive inspection
5. safe storage outside executable web paths
6. forced-download headers for served files

Recommended implementation note:

- never rely only on the user-provided filename

---

## Practical Operational Rule

For the current platform:

- allow normal document, dataset, image, audio, and video formats
- block executable, installer, and script payloads
- block direct executable URLs
- keep `Software Application` limited to metadata, repository, documentation, or landing-page style URLs

This is the cleanest way to preserve the taxonomy without turning KO ingestion into a binary distribution channel.
