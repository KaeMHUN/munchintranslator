@echo off
chcp 65001 >nul
title Munchkin Digital - Magyar Nyelv Telepítő
echo =============================================
echo  Munchkin Digital - Magyar Nyelv Telepítő
echo =============================================
echo.

set "GAME_DIR=%~dp0"
set "LOCAL_DIR=%GAME_DIR%\Munchkin_Data\StreamingAssets\Localization"
set "INSTALL_DIR=%~dp0data"
set "CACHE_DIR=%USERPROFILE%\AppData\LocalLow\Unity\Dire Wolf Digital_Munchkin\localization"

rmdir /S /Q data
mkdir data
curl --output data/win --url https://raw.githubusercontent.com/KaeMHUN/munchintranslator/refs/heads/main/data/win
curl --output data/android --url https://raw.githubusercontent.com/KaeMHUN/munchintranslator/refs/heads/main/data/android
curl --output data/ios --url https://raw.githubusercontent.com/KaeMHUN/munchintranslator/refs/heads/main/data/ios
curl --output data/osx --url https://raw.githubusercontent.com/KaeMHUN/munchintranslator/refs/heads/main/data/osx



if not exist "%GAME_DIR%" (
    echo HIBA: Nem talalhato a jatek konyvtara!
    echo Keresett: %GAME_DIR%
    echo.
    echo Kerlek add meg a jatek konyvtaranak eleresi utvonalat:
    set /p GAME_DIR="Utvonal: "
    set "LOCAL_DIR=%GAME_DIR%\Munchkin_Data\StreamingAssets\Localization"
    if not exist "%LOCAL_DIR%" (
        echo HIBA: Nem talalhato a localization konyvtar!
        pause
        exit /b 1
    )
)

echo 1. Eredeti allomanyok mentese...
for %%p in (win osx android ios) do (
    if exist "%LOCAL_DIR%\%%p\localization" (
        if not exist "%LOCAL_DIR%\%%p\localization.original" (
            copy /Y "%LOCAL_DIR%\%%p\localization" "%LOCAL_DIR%\%%p\localization.original" >nul
            echo    %%p mentve
        ) else (
            echo    %%p - mar van mentes
        )
    )
)

echo.
echo 2. Magyar nyelvi fajl masolasa...
if exist "%~dp0hungarian.txt" (
    copy /Y "%~dp0hungarian.txt" "%GAME_DIR%\hungarian.txt" >nul
    echo    hungarian.txt frissitve
)

echo.
echo 3. Magyar nyelv telepitese...
for %%p in (win osx android ios) do (
    if exist "%INSTALL_DIR%\%%p" (
        copy /Y "%INSTALL_DIR%\%%p" "%LOCAL_DIR%\%%p\localization" >nul
        echo    %%p frissitve
    )
)

echo.
echo 4. Unity gyorsitotar frissitese...
if exist "%CACHE_DIR%" (
    for /d %%d in ("%CACHE_DIR%\*") do (
        if exist "%%d\__data" (
            copy /Y "%INSTALL_DIR%\win" "%%d\__data" >nul
            echo    Gyorsitotar: %%~nxd
        )
    )
)

echo.
echo =============================================
echo  Telepites kesz!
echo.
echo  Hasznalat: Inditsd el a jatekot, valaszd a "Francais" nyelvet.
echo  A jatek magyarul fog megjelenni.
echo =============================================
pause
exit /b