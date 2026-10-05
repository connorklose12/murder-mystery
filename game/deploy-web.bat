@echo off
rem Builds the game and, ONLY if the build worked, publishes it to the website (https://connorklose12.github.io/murder-mystery/).
rem A failed build never gets published, so the site can never silently stay on an old version.
cd /d "%~dp0"
call build-web.bat
if errorlevel 1 (
    echo.
    echo ===== NOT PUBLISHED: the build failed, so the website was left alone. =====
    exit /b 1
)
cd ..
rem the publishing tool needs a package.json in this folder (without one it crashes before it starts)
if not exist package.json echo { "name": "murder-mystery", "private": true, "version": "1.0.0" }> package.json
call npx gh-pages -d MyProject/wwwroot -r https://github.com/connorklose12/murder-mystery.git
if errorlevel 1 (
    echo.
    echo ===== PUBLISH FAILED: read the error above. =====
    exit /b 1
)
echo.
echo ===== PUBLISHED. Wait about a minute, then reload the page on your phone. The "build" time at the bottom of the page should be the time you just built. =====