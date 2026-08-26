# PyInstaller 打包配置:onedir,打包 static/ 静态资源。
# 跨平台复用的关键:datas 用目录对 ('static','static'),PyInstaller 自动遍历、
# 并在各平台正确处理路径分隔符,同一 spec 可在 macos/windows runner 上复用。
# block_cipher 已由 PyInstaller 6 移除,故不设置。

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("static", "static")],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    hiddenimports=["zeroconf", "zeroconf._utils.ipaddress"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="battmon",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # 关闭 UPX,避免杀软误报 + 保持产物稳定
    console=True,       # 保留控制台窗口(便于看到启动日志/URL),非 GUI
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="battmon",
)