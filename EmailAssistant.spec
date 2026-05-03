# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Email Assistant macOS .app
# Build with:  ./build_app.sh

import os
block_cipher = None

a = Analysis(
    ['launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
    ],
    hiddenimports=[
        # Flask ecosystem
        'flask', 'jinja2', 'werkzeug', 'click',
        # Requests
        'requests', 'urllib3', 'certifi', 'charset_normalizer', 'idna',
        # DB / stdlib
        'sqlite3', 'email', 'email.header', 'email.utils', 'imaplib', 'html.parser',
        # pywebview
        'webview', 'webview.platforms.cocoa',
        # pyobjc required by pywebview on macOS
        'objc', 'AppKit', 'Foundation', 'WebKit',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'openai_whisper', 'whisper', 'torch', 'torchaudio',
        'numpy', 'tkinter', 'matplotlib',
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Email Assistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Email Assistant',
)

app = BUNDLE(
    coll,
    name='Email Assistant.app',
    icon='assets/icon.icns',
    bundle_identifier='com.emailassistant.app',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '1.0.0',
        'NSHumanReadableCopyright': '',
        # No LSUIElement — app shows in Dock like a normal window app
    },
)
