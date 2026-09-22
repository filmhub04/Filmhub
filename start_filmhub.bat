@echo off
rem Lance FilmHub en arriere-plan et le surveille (redemarrage automatique).
rem Ce script se ferme immediatement ; le veilleur tourne en tache de fond.
cd /d "C:\Users\Micro Host\Desktop\FILMS"
start "" wscript.exe "watch_filmhub.vbs"