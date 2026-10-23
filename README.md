# README.md

```markdown
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
```

---

### 4. Getting Started

#### Server Setup
1. Prerequisites: Python 3.10+ installed.
2. Navigate to the server folder and install dependencies:
   ```bash
   cd server
   pip install -r requirements.txt
   ```
3. Run the development server:
   ```bash
   python run.py
   ```
4. Access the portal:
   - Web Portal: `http://127.0.0.1:5000/login`
   - Default Admin Credentials:
     - **Email**: `admin@kaalk.ir`
     - **Password**: `Admin@12345`
   - Interactive API Documentation (Swagger): `http://127.0.0.1:5000/docs`

#### AutoCAD Plugin Compilation
The assembly compiles via `csc.exe` (C# 5 / .NET 4.x), requiring no external NuGet packages:
```powershell
./build/Build.ps1 -Version "0.4.1" -Commit "local"
```
The compiled output is placed in `dist/0.4.1/KaalkAssetManager.dll`.

#### Loading in AutoCAD 2018
1. Launch AutoCAD 2018.
2. Run the `NETLOAD` command and select `KaalkAssetManager.dll`.
3. Type `KAALK` to display the version, verify the active session, and toggle the palette.

---

<br><hr><br>

<a name="persian-documentation"></a>
## Persian Documentation (مستندات فارسی)

### ۱. درباره پروژه
سیستم مدیریت دارایی **KAALK** یک پلتفرم جامع برای کشف، دانلود، نصب و اجرای خودکار ابزارهای تخصصی اتوکد (نظیر فایل‌های AutoLISP، بلوک‌های دینامیک، الگوهای هاشور و ابزارهای مهندسی) است. ایده بنیادین پروژه این است که کاربر بدون خروج از محیط ترسیم اتوکد و بدون نیاز به وب‌گردی، به تمامی ابزارها دسترسی داشته باشد.

این پروژه از دو بخش اصلی تشکیل شده است:
1. **کلاینت افزونه اتوکد (`KaalkAssetManager.dll`)**: توسعه‌یافته بر پایه زبان C# 5 و دات‌نت فریم‌ورک 4 با معماری строго ۵ لایه و بدون وابستگی به پکیج‌های خارجی NuGet.
2. **سرور پلتفرم (`server/`)**: سامانه سبک، ماژولار و بسیار سریع مبتنی بر Python، FastAPI، دیتابیس SQLite3 و قالب‌های Jinja2.

---

### ۲. معماری و اصول فنی

#### معماری افزونه اتوکد
افزونه کلاینت از قانون معماری یک‌طرفه پیروی می‌کند که قبل از هر کامپایل توسط اسکریپت `Check-Architecture.cmd` بازرسی می‌شود:
* **لایه امنیت (Security)**: مسئول رمزنگاری اطلاعات سشن کاربر با Windows DPAPI، قوانین اعتبارسنجی گذرواژه و خواندن توکن JWT بدون اینترنت. (فاقد هرگونه وابستگی به شبکه یا UI).
* **لایه هسته (Core)**: مدیریت ارتباط HTTP، حافظه کش دیسک (`%LOCALAPPDATA%\KAALK\cache`)، پردازش مانیفست‌ها و مدیریت وضعیت نشست. (فاقد وابستگی به اتوکد یا WPF).
* **لایه ارائه‌دهنده‌ها (Presenters)**: هماهنگ‌کننده تعاملات کاربر، جریان جستجو و فیلتر کردن کاتالوگ بدون وابستگی به فرمت‌های تصویری و انواع WPF.
* **لایه ظاهر (UI)**: فرم‌ها و کنترل‌های استایل‌دار WPF با تم تیره، مدیریت پیام‌ها و بازخوردها. (بدون دسترسی مستقیم به امنیت یا شبکه).
* **لایه میزبان (Host)**: نقطه اتصال افزونه به اتوکد، ثبت دستورات خط فرمان (`KAALK` و `KAALKLOGOUT`) و پیکربندی شبکه (اجبار پروتکل TLS 1.2+).

#### معماری سرور (FastAPI + SQLite)
* **سیستم مانیفست دومرحله‌ای (Two-Tier Manifest)**:
  * **کاتالوگ سبک (مرحله اول)**: ارسال خلاصه اقلام فروشگاه برای لود آنی و بدون لگ لیست‌ها.
  * **مانیفست تفصیلی (مرحله دوم)**: ارسال تاریخچه نسخه‌ها، تغییرات هر نسخه (Release Notes)، دستورات اجرایی، و مدیاهای آموزشی تنها با کلیک روی محصول.
* **اتوماسیون بسته‌بندی پکیج‌ها (`PackageService`)**:
  * دریافت چند فایل سورس به‌صورت همزمان (`.lsp`، `.dcl`، `.shx`، `.dwg`) و زیپ خودکار آن‌ها همراه با شناسه `package.json`.
  * تغییر سایز استاندارد آیکون به دو اندازه ۳۲×۳۲ و ۶۴×۶۴ پیکسل با استفاده از ماژول Pillow.
  * محاسبه خودکار هش SHA-256 و مدیریت نگهداری نسخه‌های تفکیک‌شده (`{version}.zip`) و نسخه پایدار جاری (`latest.zip`).
* **پرتال وب و پنل مدیریت**:
  * مدیریت پلن‌های اشتراک داینامیک به واحد تومان با محاسبه تخفیف‌ها و پلن‌های مناسبتی.
  * جریان شبیه‌سازی‌شده پرداخت مالی امن جهت جلوگیری از ارتقای غیرمجاز بدون تسویه حساب.
  * پنل مدیریت اختصاصی جهت تعلیق کاربران، ویرایش سطح دسترسی ادمین و حذف نسخه‌های باگ‌دار با بازگردانی خودکار (Rollback).

---

### ۳. راهنمای راه‌اندازی و استفاده

#### راه‌اندازی سرور پایتون
۱. مطمئن شوید پایتون نسخه 3.10 به بالا روی سیستم نصب است.  
۲. به پوشه `server` رفته و پیش‌نیازها را نصب کنید:
```bash
cd server
pip install -r requirements.txt
```
۳. سرور را اجرا کنید:
```bash
python run.py
```
۴. پرتال در آدرس `http://127.0.0.1:5000` در دسترس خواهد بود.  
مشخصات ورود پیش‌فرض مدیر:
* **ایمیل**: `admin@kaalk.ir`
* **رمز عبور**: `Admin@12345`

مستندات تعاملی Swagger API:  
`http://127.0.0.1:5000/docs`

#### بیلد و کامپایل افزونه اتوکد
کامپایل از طریق کامپایلر بومی ویندوز `csc.exe` انجام می‌شود:
```powershell
./build/Build.ps1 -Version "0.4.1" -Commit "local"
```
خروجی در مسیر `dist/0.4.1/KaalkAssetManager.dll` قرار خواهد گرفت.

#### بارگذاری داخل اتوکد 2018
۱. اتوکد 2018 را باز کنید.  
۲. دستور `NETLOAD` را تایپ کرده و فایل `KaalkAssetManager.dll` را انتخاب کنید.  
۳. دستور `KAALK` را در خط فرمان وارد کنید تا مشخصات نسخه و سشن فعال چاپ شده و پالت باز شود.

---

### ۴. استانداردهای توسعه
- **زبان کدنویسی**: تمام کامنت‌ها، نام متغیرها، رشته‌ها و فایل‌های پروژه باید منحصراً به زبان انگلیسی و بدون کاراکترهای تزئینی/ایموجی باشند.
- **بررسی لایه‌ها**: قبل از هر Commit، اجرای اسکریپت `Check-Architecture.cmd` الزامی است.
- **نسخه‌گذاری**: شماره نسخه پایه نرم‌افزار در فایل `version.txt` تعیین می‌شود.
```
