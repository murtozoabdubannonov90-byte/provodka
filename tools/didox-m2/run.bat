@echo off
REM SOLIDUM M-2 ishonchnoma - Windows uchun bir tugmali ishga tushirish
setlocal
cd /d "%~dp0"

if not exist config.json (
  echo config.json topilmadi. Namunadan nusxa olinmoqda...
  copy config.example.json config.json >nul
  echo config.json yaratildi - papka yo'llari va Didox tokenini to'ldiring.
  notepad config.json
  goto :eof
)

echo.
echo [1/3] Sertifikatlar o'qilmoqda...
python run.py keys
if errorlevel 1 echo    (sertifikat topilmadi - kalitlar.md izohlarini ko'ring)

echo.
echo [2/3] Oxirgi ishonchnoma o'qilmoqda...
python run.py last || goto :error

echo.
echo Yuqoridagi ishonchli shaxs ma'lumotlarini tekshiring.
pause

echo.
echo [3/3] Yangi M-2 hujjati tayyorlanmoqda...
python run.py build || goto :error

echo.
echo Tayyor. Yuborish uchun yuqorida ko'rsatilgan `send --confirm` buyrug'ini ishlating.
pause
goto :eof

:error
echo.
echo Xatolik yuz berdi.
pause
