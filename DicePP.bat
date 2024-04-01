@echo off
Title DicePP骰娘后端 - v1.4.2β
:start
set GIT_PYTHON_REFRESH=quiet
set PYTHON_EXE=..\Python\python.exe
if exist %PYTHON_EXE% (
	%PYTHON_EXE% bot.py
) else (
	python bot.py
)
echo 开始重启
goto start