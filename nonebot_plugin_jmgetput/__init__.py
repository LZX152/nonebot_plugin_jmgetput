from nonebot import get_driver, logger, on_shell_command, on_regex
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.params import RegexMatched
from nonebot.typing import T_State
from nonebot.rule import ArgumentParser
from collections import deque
from nonebot.adapters.onebot.v11 import  MessageEvent
from nonebot.exception import FinishedException

import re
import jmcomic
from jmcomic import JmModuleConfig, DirRule
from jmcomic import Img2pdfPlugin

import requests
import os
import time
from pathlib import Path

from uvicorn.loops import asyncio
from jmcomic import JmModuleConfig

from fuzzywuzzy import fuzz
from pathlib import Path

# 你需要写一个函数，把字段名作为key，函数作为value，加到JmModuleConfig.AFIELD_ADVICE这个字典中
JmModuleConfig.AFIELD_ADVICE['myname'] = lambda album: f'[{album.id}] {album.title}'

backup_group = get_driver().config.dict().get('backup_group', [])
backup_command = get_driver().config.dict().get('backup_command', "备份群文件")
backup_maxsize = get_driver().config.dict().get('backup_maxsize', 300)
backup_minsize = get_driver().config.dict().get('backup_minsize', 0.01)
backup_temp_files = get_driver().config.dict().get('backup_temp_files', True)
backup_temp_file_ignore = get_driver().config.dict().get(
    'backup_temp_file_ignore', [".gif", ".png", ".jpg", ".mp4"])


linker_parser = ArgumentParser(add_help=False)
linker = on_shell_command(backup_command, parser=linker_parser, priority=1)

upload_command = get_driver().config.dict().get('upload_command', "上传群文件")
upload_parser = ArgumentParser(add_help=False)
upload = on_shell_command(upload_command, parser=upload_parser, priority=1)

jm_download_command = get_driver().config.dict().get('jm_download_command', "jm")
jm_download_parser = ArgumentParser(add_help=False)
jm_download = on_shell_command(jm_download_command, parser=jm_download_parser, priority=1)



class EventInfo:
    fdindex = -1
    fsuccess = fjump = fsizes = 0
    fdtoolarge = []
    fbroken = []
    fdnames = []

    def __init__(self) -> None:
        ...

    def init(self) -> None:
        self.fdindex = -1
        self.fsuccess = self.fjump = self.fsizes = 0
        self.fdtoolarge = []
        self.fbroken = []
        self.fdnames = []




@jm_download.handle()
async def handle_jm_download(bot: Bot, event: MessageEvent):
    """统一入口函数，控制整个JM下载流程"""
    try:
        # 1. 获取并验证输入
        jm_code = await parse_jm_input(event)
        if not jm_code:
            return  # 已发送错误消息并结束

        # 2. 发送处理中提示
        await bot.send(event, f"⏳ 正在下载 {jm_code}...")

        # 3. 执行下载
        pdf_path = await download_jm_album(bot,jm_code)
        logger.debug("文件下载完成:" + pdf_path)
        # await bot.send(event, f"{pdf_path}")
        # 4. 上传文件到群
        if pdf_path:
            await upload_jm_to_group(bot, event, pdf_path)
        else:
            await jm_download.finish(f"❌ 下载失败: 未生成PDF文件")

    except FinishedException:
        pass  # 忽略正常的结束异常
    except Exception as e:
        logger.error(f"JM下载流程异常: {e}")
        await jm_download.finish(f"⚠️ 下载失败: {str(e)}")
        return

async def SaveToDisk(bot, ff, fdpath, EIF, gid):
    fname = ff["file_name"]
    fid = ff["file_id"]
    fbusid = ff["busid"]
    fsize = ff["file_size"]
    fpath = Path(fdpath, fname)

    if fsize/1024/1024 < backup_minsize:
        return

    if fsize/1024/1024 > backup_maxsize:
        EIF.fdtoolarge.append(
            EIF.fdnames[EI.fdindex] + "/" + fname)
        return

    if not Path(fpath).exists():
        try:

            finfo = await bot.get_group_file_url(group_id=gid, file_id=str(fid), bus_id=int(fbusid))
            url = finfo['url']
            req = requests.get(url)

            if not Path(fdpath).exists():
                os.makedirs(fdpath)
            with open(fpath, 'wb') as mfile:
                mfile.write(req.content)
            EIF.fsizes += fsize
            EIF.fsuccess += 1
        except Exception as e:
            EIF.fbroken.append(fdpath + "/" + fname)
            print(e)
            logger.debug("文件获取不到/已损坏:" + fdpath + "/" + fname)
    else:
        EIF.fsizes += Path(fpath).stat().st_size
        EIF.fjump += 1


async def createFolder(bot, root_dir, gid):
    root = await bot.get_group_root_files(group_id=gid)
    folders = root.get("folders")
    fdnames = []
    fdnames.extend([i["folder_name"] for i in folders])

    for parent, dirs, files in os.walk(root_dir):
        if dirs:
            for fd_name in dirs:
                if fd_name not in fdnames:
                    print(fd_name)
                    await bot.create_group_file_folder(
                        group_id=gid, name=fd_name, parent_i="/")


async def upload_files(bot, gid, folder_id, root_dir):
    group_root = await bot.get_group_files_by_folder(group_id=gid, folder_id=folder_id)
    files = group_root.get("files")
    filenames = []
    if files:
        filenames = [ff["file_name"] for ff in files]
    if os.path.exists(root_dir):
        for entry in os.scandir(root_dir):
            if entry.is_file() and entry.name not in filenames:
                absolute_path = Path(root_dir).resolve().joinpath(entry.name)

                await bot.upload_group_file(
                    group_id=gid, file=str(absolute_path), name=entry.name, folder=folder_id)

EI = EventInfo()

async def upload_file_from_message(bot: Bot, event: GroupMessageEvent, file_path: str, folder_id: str = "/"):
    """根据用户提供的文件路径或URL上传文件到群文件"""
    try:
        threshold = 80  # 相似度阈值（0~100）

        pdf_dir = Path("E:/tools/image2pdf-main/books/pdf")
        matched_files = []
        for file in pdf_dir.glob("*.pdf"):
            ratio = fuzz.ratio(file_path, file.name)
            if ratio >= threshold:
                matched_files.append((file, ratio))
        # 按相似度排序
        matched_files.sort(key=lambda x: x[1], reverse=True)

        absPath = matched_files[0][0]

        # 检查文件是否存在
        if not os.path.exists(absPath):
            await bot.send(event, f"文件 {file_path} 不存在！")
            return False
        else:
            await bot.send(event, f"⏳ 正在上传: {file_path}")

        # 上传文件
        await bot.upload_group_file(
            group_id=event.group_id,
            file=str(absPath),
            name=os.path.basename(file_path),
            folder=folder_id,
        )
        return True
    except Exception as e:
        pass

@linker.handle()
async def link(bot: Bot, event: GroupMessageEvent, state: T_State):
    EI.init()
    gid = event.group_id
    if str(gid) in backup_group or backup_group == []:
        args = vars(state.get("_args"))
        logger.debug(args)

        await bot.send(event, "备份中,请稍后…(不会备份根目录文件,请把重要文件放文件夹里)")
        tstart = time.time()
        root = await bot.get_group_root_files(group_id=gid)
        folders = root.get("folders")
        if backup_temp_files:
            files = root.get("files")
            fdpath = "./qqgroup/" + str(event.group_id)
            if files:
                for ff in files:
                    suf = Path(ff["file_name"]).suffix
                    if suf in backup_temp_file_ignore:
                        continue

                    await SaveToDisk(bot, ff, fdpath, EI, gid)

        # 广度优先搜索
        dq = deque()

        if folders:
            dq.extend([i["folder_id"] for i in folders])
            EI.fdnames.extend([i["folder_name"] for i in folders])

        while dq:
            EI.fdindex += 1
            _ = dq.popleft()
            logger.debug("下一个搜索的文件夹：" + _)
            root = await bot.get_group_files_by_folder(group_id=gid, folder_id=_)

            fdpath = "./qqgroup/" + \
                str(gid) + "/" + EI.fdnames[EI.fdindex]

            file = root.get("files")

            if file:
                for ff in file:
                    await SaveToDisk(bot, ff, fdpath, EI, gid)

        if len(EI.fdtoolarge) == 0:
            EI.fdtoolarge = "无"
        else:
            EI.fdtoolarge = "\n".join(EI.fdtoolarge)

        if len(EI.fbroken) == 0:
            EI.fbroken = ""
        else:
            EI.fbroken = "检测到损坏文件:" + '\n'.join(EI.fbroken)

        EI.fsizes = round(EI.fsizes/1024/1024, 2)
        tsum = round(time.time()-tstart, 2)

        await linker.finish("此次备份耗时%2d秒; 共备份%d个文件,跳过已备份%d个文件, 累计备份大小%.2f M,\n未备份大文件列表(>%dm):\n%s\n%s" % (tsum, EI.fsuccess, EI.fjump, EI.fsizes, backup_maxsize, EI.fdtoolarge, EI.fbroken))

UPLOAD_BASE_DIR = Path(r"E:\tools\image2pdf-main\books")
ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.png'}  # 可选：限制上传文件类型
@upload.handle()
async def handle_upload(bot: Bot, event: MessageEvent):
    """统一入口函数，控制整个上传流程"""
    try:
        # 1. 获取并验证输入
        file_input = await parse_user_input(event)
        if not file_input:
            return  # 已发送错误消息并结束
        
        # 2. 构建安全路径
        target_path = await validate_file_path(file_input)
        if not target_path:
            return  # 已发送错误消息并结束
        
        # 3. 执行上传
        if target_path.is_file():
            await handle_single_file(bot, event, target_path)
        else:
            await handle_directory(bot, event, target_path)
            
    except FinishedException:
        pass  # 忽略正常的结束异常
    except Exception as e:
        logger.error(f"上传流程异常: {e}")
        await upload.finish(f"⚠️ 系统错误: 请稍后再试")


async def parse_user_input(event: MessageEvent) -> str:
    """解析用户输入并返回清理后的路径"""
    try:
        msg = event.get_plaintext().strip()
        return msg.split(upload_command, 1)[1].strip() if upload_command in msg else msg
    except Exception as e:
        logger.error(f"输入解析失败: {e}")
        await upload.finish("❌ 无效输入格式，请使用: /上传文件 文件名")
        return ""

async def validate_file_path(rel_path: str) -> Path:
    """验证并返回安全的绝对路径"""
    try:
        base_dir = Path(r"E:\tools\image2pdf-main\books\pdf")
        target_path = (base_dir / rel_path).resolve()
        
        # 安全校验
        if not str(target_path).startswith(str(base_dir)):
            await upload.finish("❌ 禁止访问该路径")
            return None
            
        if not target_path.exists():
            await upload.finish(f"❌ 路径不存在: {base_dir}")
            return None
            
        return target_path
    except Exception as e:
        logger.error(f"路径验证失败: {e}")
        await upload.finish("❌ 无效文件路径")
        return None

async def handle_single_file(bot: Bot, event: MessageEvent, file_path: Path):
    """处理单个文件上传"""
    try:
        await bot.send(event, f"⏳ 正在上传: {file_path}")
        
        # 调用实际的上传逻辑
        success = await upload_file_from_message(bot, event, str(file_path))
        
        # 统一结束点
        msg = f"✅ 上传成功: {file_path.name}" if success else f"❌ 上传失败: {file_path.name}"
        await upload.finish(msg)
        return True
        
    except Exception as e:
            pass
async def handle_directory(bot: Bot, event: MessageEvent, dir_path: Path):
    """处理目录上传"""
    try:
        files = [f for f in dir_path.iterdir() if f.is_file()]
        if not files:
            await upload.finish("⚠️ 目录为空")
            return
            
        await bot.send(event, f"📁 开始上传 {len(files)} 个文件...")
        
        results = []
        for file in files:
            try:
                success = await upload_file_from_message(bot, event, str(file))
                results.append(success)
                await asyncio.sleep(0.5)  # 防止速率限制
            except Exception as e:
                pass
        
        # 统一结束点
        success_count = sum(results)
        await upload.finish(
            f"📊 上传完成\n"
            f"✅ 成功: {success_count}\n"
            f"❌ 失败: {len(results) - success_count}"
        )
        
    except Exception as e:
        pass
    

async def parse_jm_input(event: MessageEvent) -> str:
    """解析用户输入并返回JM编号"""
    try:
        msg = event.get_plaintext().strip()
        # 提取JM编号部分
        input_part = msg.split(jm_download_command, 1)[1].strip() if jm_download_command in msg else msg

        # 提取数字部分
        match = re.search(r'(\d+)', input_part)
        if not match:
            await jm_download.finish("❌ 无效JM编号格式，请使用: 下载JM 编号 (如: 下载JM 123456)")
            return None
        jm_code = f"JM{match.group(1)}"
        return jm_code

    except Exception as e:
        logger.error(f"JM编号解析失败: {e}")
        await jm_download.finish("❌ 无效输入格式，请使用: 下载JM 编号")
        return None


async def download_jm_album(bot: Bot,jm_code: str) -> Path:
    """下载JM相册并返回PDF文件路径"""

    try:
        # 加载配置
        option = jmcomic.JmOption.from_file("E:/tools/image2pdf-main/config.yml")
        # 下载相册
        result = jmcomic.download_album(jm_code, option)
        album = result[0] if isinstance(result, tuple) else result  # 兼容新旧版本
        # album = jmcomic.download_album(jm_code, option)
        if album is None:
            raise Exception(f"JM下载失败: {jm_code}")

        # 使用相册标题作为文件名（photo=None）
        filename = DirRule.apply_rule_directly(album, None, "Atitle")
        pdf_path = f"{filename}.pdf"
        return pdf_path
    except Exception as e:
        logger.error(f"JM下载失败: {e}")
        raise Exception(f"下载文件失败: {str(e)}")

async def upload_jm_to_group(bot: Bot, event: MessageEvent, pdf_path: Path):
    """将下载的JM PDF上传到群文件"""
    try:
        success = await upload_file_from_message(bot, event, str(pdf_path))

        msg = f"✅ 上传成功: {pdf_path}" if success else f"❌ 上传失败: {pdf_path}"
        await jm_download.finish(msg)

    except Exception as e:
        logger.error(f"JM上传失败: {e}")