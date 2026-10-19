@echo off
REM Launch the Android social uploader.
REM
REM Usage:
REM   start.bat            process every job, in continuous polling mode
REM   start.bat 25         process a single job (id 25)
REM
REM API keys and the backend URL are read from the .env file.

if "%~1"=="" (
    python job_runner.py
) else (
    python job_runner.py --job-id %~1
)
