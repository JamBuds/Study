; Inno Setup script - compile with:  iscc installer.iss   (after running PyInstaller)
[Setup]
AppName=StudyBuddy
AppVersion=1.0
DefaultDirName={autopf}\StudyBuddy
DefaultGroupName=StudyBuddy
OutputDir=installer
OutputBaseFilename=StudyBuddy-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesInstallMode=x64compatible

[Files]
Source: "dist\StudyBuddy\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\StudyBuddy"; Filename: "{app}\StudyBuddy.exe"
Name: "{autodesktop}\StudyBuddy"; Filename: "{app}\StudyBuddy.exe"

[Run]
Filename: "{app}\StudyBuddy.exe"; Description: "Launch StudyBuddy"; Flags: nowait postinstall skipifsilent
