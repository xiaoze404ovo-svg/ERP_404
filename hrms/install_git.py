import urllib.request, os, subprocess, sys

url = "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.2/Git-2.47.1.2-64-bit.exe"
installer = os.path.join(os.environ['TEMP'], 'git_installer.exe')

print("正在下载 Git 安装程序...")
urllib.request.urlretrieve(url, installer)
print("下载完成，正在安装（静默安装）...")
subprocess.run([installer, '/SILENT', '/VERYSILENT', '/NORESTART', '/SUPPRESSMSGBOXES', 
                '/DIR=C:\\Program Files\\Git'], check=True)
print("Git 安装完成！")
