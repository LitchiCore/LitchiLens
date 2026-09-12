param([Parameter(Mandatory=$true)][string]$Server,[int]$LocalPort=8769)
# 管理界面只经 SSH 隧道开放到本机，不在公网增加登录页。
Write-Host "SSH 隧道保持运行后，在浏览器打开 http://127.0.0.1:$LocalPort/"
& ssh -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -N -L "127.0.0.1:${LocalPort}:127.0.0.1:8769" $Server
