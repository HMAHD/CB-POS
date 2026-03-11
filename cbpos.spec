# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [
    ('cbpos/assets', 'cbpos/assets'),
    ('cbpos/ui/styles', 'cbpos/ui/styles'),
    ('cbpos/i18n', 'cbpos/i18n'),
    ('alembic.ini', '.'),
    ('alembic', 'alembic'),
]
binaries = []
hiddenimports = [
    'sqlalchemy.sql.default_comparator',
    'sqlalchemy.ext.baked',
    'sqlalchemy.ext.declarative',
    'sqlalchemy.orm.util',
    'sqlalchemy.orm.state',
    'sqlalchemy.orm.strategies',
    'sqlalchemy.orm.loading',
    'sqlalchemy.orm.identity',
    'sqlalchemy.orm.dependency',
    'sqlalchemy.orm.attributes',
    'sqlalchemy.orm.events',
    'sqlalchemy.orm.instrumentation',
    'sqlalchemy.orm.collections',
    'sqlalchemy.orm.scoping',
    'sqlalchemy.orm.session',
    'sqlalchemy.orm.sync',
    'sqlalchemy.orm.unitofwork',
    'sqlalchemy.orm.query',
    'sqlalchemy.orm.persistence',
    'sqlalchemy.orm.mapper',
    'sqlalchemy.orm.interfaces',
    'sqlalchemy.orm.exc',
    'sqlalchemy.orm.evaluator',
    'sqlalchemy.orm.dynamic',
    'sqlalchemy.orm.descriptor_props',
    'sqlalchemy.orm.decl_api',
    'sqlalchemy.orm.context',
    'sqlalchemy.orm.base',
    'sqlalchemy.orm.attributes',
    'escpos',
    'escpos.printer',
    'usb.core',
    'usb.backend.libusb1',
]

# Collect all for escpos just in case
tmp_ret = collect_all('escpos')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='cbpos',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='cbpos/assets/ico/cbpos_multi.ico'
)
