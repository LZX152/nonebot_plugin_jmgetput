<div align="center">


# nonebot_plugin_jmgetput
一款基于NoneBot2和JMComic-Crawler-Python的插件，用来上传文件到qq群
A plugin based on NoneBot2 and JMComic-Crawler-Python to upload jmcomic files or files in qq group
</div>

基于 
<div align="center">
[NoneBot2](https://github.com/nonebot/nonebot2)
https://github.com/Yuelioi/nonebot-plugin-backup
https://github.com/hect0x7/JMComic-Crawler-Python
</div>
的插件，来上传QQ群文件，同时集成了jm指令，用来下载jm中的资源并发送到QQ群聊中

## 用途

上传QQ群文件

访问jm

下载jm文件

将jm文件发送到QQ群中

## 用法
安装该插件
```
pip install .
```
通过/上传群文件 path/to/file，上传文件到qq群，要修改代码中路径的位置
通过在群聊中发送/jm xxxxxx指令，来下载对应的文件