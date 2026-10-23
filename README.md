# KAALK Asset Manager

An enterprise-grade asset manager and store integration for **AutoCAD 2018+**, featuring an embedded WPF palette client and a lightweight, high-performance **FastAPI + SQLite** backend portal.

---

## Language / زبان
- [English Documentation](#english-documentation)
- [مستندات فارسی](#persian-documentation)

---

<a name="english-documentation"></a>
## English Documentation

### 1. Overview
KAALK Asset Manager provides a seamless in-app marketplace and package runtime directly inside AutoCAD. Users can discover, install, update, and run CAD tools, dynamic blocks, hatch patterns, and LISP routines without leaving their drawing environment.

The system is split into two components:
1. **AutoCAD Plugin Client (`KaalkAssetManager.dll`)**: A strictly layered C# 5 / .NET 4.x assembly compiled natively via `csc.exe` and hosted inside AutoCAD via an `ElementHost` WPF palette.
2. **Platform Server (`server/`)**: A fast, asynchronous backend powered by FastAPI, SQLite, and Jinja2 managing authentication, two-tier catalog manifests, multi-file package builds, and subscription billing.

---

### 2. Architecture & Design Principles

#### Client Architecture (AutoCAD Plugin)
The plugin strictly follows a unidirectional 5-layer boundary enforced by automated CI checks (`Check-Architecture.cmd`):
- **Security**: Windows DPAPI encryption (`session.dat`), password validation rules, and offline JWT reading. Zero network/UI dependencies.
- **Core**: API client, session management, catalog and detail manifest services, local disk caching (`%LOCALAPPDATA%\KAALK\cache`). Zero UI/AutoCAD dependencies.
- **Presenters**: UI-independent coordination, screen workflows, search filtering, and view state management.
- **UI**: Modern dark WPF views, controls, and error message translations. Zero direct network/security access.
- **Host**: AutoCAD API integration, `PaletteSet` wrapper, commands (`KAALK`, `KAALKLOGOUT`), and process-level network initialization (TLS 1.2+).

#### Server Architecture (FastAPI + SQLite)
- **Two-Tier Manifest Engine**:
  - `Tier 1 (GET /api/v1/catalog)`: Lightweight catalog index for ultra-fast list rendering.
  - `Tier 2 (GET /api/v1/assets/{id})`: Comprehensive manifest requested on-demand, containing command aliases, version changelogs, release notes, and tutorial media.
- **Package Automation (`package_service.py`)**:
  - Compiles uploaded source files (`.lsp`, `.dcl`, `.shx`, `.dwg`) into a structured ZIP containing an internal `package.json`.
  - Automatically resizes icons into standard `32x32` and `64x64` formats using Pillow.
  - Generates SHA-256 integrity checksums and maintains both versioned (`{version}.zip`) and pointer (`latest.zip`) archives.
- **Web Portal & Administration**:
  - Dynamic subscription plans with Iranian Toman currency formatting, duration limits, and promotional discount badges.
  - Simulated payment gateway flow (`/checkout` -> `/payment/gateway` -> `/payment/callback`).
  - Administration console (`/admin`) for user access control, account suspension, plan management, and buggy version rollback.

---

### 3. Repository Structure

```text
├── .github/workflows/
│   └── build.yml               # Automated CI build & packaging pipeline
├── build/
│   └── Build.ps1               # Automated csc.exe compilation script
├── libs/
│   └── autocad2018/            # AutoCAD .NET reference assemblies (Private)
├── Security/                   # Layer 1: Encryption, tokens, validation
├── Core/                       # Layer 2: API, JSON, Session, Catalog cache
├── Presenters/                 # Layer 3: Screen coordination & business flow
├── UI/                         # Layer 4: WPF views, themes, text mapping
├── Host/                       # Layer 5: AutoCAD commands, entry point, palette
├── server/                     # FastAPI backend application
│   ├── app/
│   │   ├── config.py           # Paths, security parameters
│   │   ├── database.py         # SQLite schema initialization and seeders
│   │   ├── security.py         # Passlib/Bcrypt and JWT handling
│   │   ├── routers/            # Auth API, Store API, Web Portal, Admin
│   │   ├── services/           # Package compilation and icon processing
│   │   └── templates/          # Dark-themed Jinja2 HTML templates
│   ├── storage/                # Stored package archives and media assets
│   ├── requirements.txt        # Python backend dependencies
│   └── run.py                  # Server bootstrap runner
├── Check-Architecture.cmd      # Architectural boundary enforcement script
├── version.txt                 # Major.Minor version seed
└── CHANGELOG.md                # Detailed project change log
