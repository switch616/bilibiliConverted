import os
import json
import asyncio
import subprocess
import shutil
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

# 加载配置
load_dotenv()


class BilibiliCacheConverter:
    def __init__(self):
        self.cache_root = os.getenv("BILIBILI_CACHE_DIR").strip()
        self.output_root = os.getenv("OUTPUT_MP4_DIR").strip()
        self.max_workers = int(os.getenv("MAX_WORKERS", 3))
        self.skip_existing = os.getenv("SKIP_EXISTING", "True").lower() == "true"

        os.makedirs(self.output_root, exist_ok=True)
        if not os.path.isdir(self.cache_root):
            raise Exception(f"缓存目录不存在：{self.cache_root}")

        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

    def clean_name(self, name: str) -> str:
        """清理文件夹/文件名非法字符"""
        invalid_chars = ["\\", "/", ":", "*", "?", '"', "<", ">", "|"]
        for c in invalid_chars:
            name = name.replace(c, "")
        return name.strip()

    def parse_video_info(self, folder_path):
        """
        解析规则：
        bvid        → 课程文件夹名
        groupTitle  → 写入00_课程信息.txt
        p           → 集序号（内部排序用）
        tabName     → 最终视频文件名
        """
        p_index = 0
        bvid = "UnknownBV"
        tab_name = os.path.basename(folder_path)
        group_title = "未命名课程"
        course_link = ""

        for info_file in ["videoInfo.json", ".videoInfo"]:
            info_path = os.path.join(folder_path, info_file)
            if os.path.exists(info_path):
                try:
                    with open(info_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    # 集序号
                    p_index = int(data.get("p", 0))
                    # BV号 作为课程文件夹
                    bvid = data.get("bvid", "UnknownBV").strip()
                    # 视频单集名
                    tab_name = data.get("tabName", data.get("title", tab_name)).strip()
                    # 课程全称
                    group_title = data.get("groupTitle", "未命名课程").strip()
                    # 课程链接
                    course_link = "https://www.bilibili.com/video/" + bvid
                    break
                except:
                    continue

        bvid = self.clean_name(bvid)
        tab_name = self.clean_name(tab_name)
        group_title = self.clean_name(group_title)
        course_link = course_link.strip()
        return p_index, bvid, tab_name, group_title, course_link

    def create_course_info_txt(self, course_dir, group_title, course_link):
        """在课程文件夹生成 00_课程信息.txt，保证排序第一"""
        txt_path = os.path.join(course_dir, "00_课程信息.txt")
        if not os.path.exists(txt_path):
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(f"{group_title}\n")
                f.write(f"课程链接：{course_link}\n")
            print(f"已生成课程说明文件：{txt_path}")

    def create_and_fix_temp_file(self, original_file: str):
        if not os.path.exists(original_file):
            return None

        # 保留原文件bak备份
        backup_path = original_file + ".bak"
        if not os.path.exists(backup_path):
            shutil.copy2(original_file, backup_path)
            print(f"已备份原文件：{os.path.basename(backup_path)}")

        # 生成临时文件，不改动源文件
        file_dir = os.path.dirname(original_file)
        file_name = os.path.splitext(os.path.basename(original_file))[0]
        temp_file = os.path.join(file_dir, f"{file_name}_temp.m4s")
        shutil.copy2(original_file, temp_file)

        # 仅修改临时文件前9字节
        try:
            with open(temp_file, "rb") as f:
                data = f.read()
            new_data = data[9:]
            with open(temp_file, "wb") as f:
                f.write(new_data)
            print(f"已创建并修复临时文件：{os.path.basename(temp_file)}")
            return temp_file
        except Exception as e:
            print(f"临时文件处理失败：{os.path.basename(temp_file)}，错误：{str(e)}")
            return None

    def merge(self, video: str, audio: str, output: str) -> bool:
        cmd = [
            "ffmpeg",
            "-i",
            video,
            "-i",
            audio,
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-y",
            output,
        ]
        try:
            # 移除 Windows 专属参数，全平台兼容
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            if result.returncode == 0 and os.path.exists(output):
                return True
            print(f"FFmpeg错误：{result.stderr[:500]}")
            return False
        except Exception as e:
            print(f"合并异常：{str(e)}")
            return False

    def find_media_files(self, folder: str):
        video_file = None
        audio_file = None
        for f in os.listdir(folder):
            full_path = os.path.join(folder, f)
            if not f.endswith(".m4s"):
                continue
            name_part = f.split(".")[0].split("-")[-1]
            if "300" in name_part:
                video_file = full_path
            if "302" in name_part:
                audio_file = full_path
        return video_file, audio_file

    def process_folder(self, folder_path: str):
        p_idx, bvid, tab_name, group_title, course_link = self.parse_video_info(
            folder_path
        )

        # 按BV号建课程文件夹
        course_dir = os.path.join(self.output_root, bvid)
        os.makedirs(course_dir, exist_ok=True)

        # 生成00_课程信息txt
        self.create_course_info_txt(course_dir, group_title, course_link)

        # 视频文件名直接用tabName，不再加序号前缀
        output_mp4 = os.path.join(course_dir, f"{tab_name}.mp4")

        if self.skip_existing and os.path.exists(output_mp4):
            print(f"跳过：{bvid} - {tab_name}")
            return

        original_video, original_audio = self.find_media_files(folder_path)
        if not original_video or not original_audio:
            print(f"缺失音视频文件：{bvid} - {tab_name}")
            return

        temp_video = self.create_and_fix_temp_file(original_video)
        temp_audio = self.create_and_fix_temp_file(original_audio)
        if not temp_video or not temp_audio:
            print(f"临时文件创建失败：{bvid} - {tab_name}")
            return

        print(f"转换中：{bvid} - {tab_name}")
        success = self.merge(temp_video, temp_audio, output_mp4)

        # 清理临时文件
        if os.path.exists(temp_video):
            os.remove(temp_video)
        if os.path.exists(temp_audio):
            os.remove(temp_audio)

        if success:
            print(f"转换成功：{output_mp4}\n")
        else:
            print(f"转换失败：{bvid} - {tab_name}\n")

    async def async_run(self):
        raw_folders = [
            os.path.join(self.cache_root, f)
            for f in os.listdir(self.cache_root)
            if os.path.isdir(os.path.join(self.cache_root, f))
        ]
        if not raw_folders:
            print("未找到视频文件夹")
            return

        # 按集数p排序，保证课程内顺序正确
        sorted_folders = sorted(raw_folders, key=lambda x: self.parse_video_info(x)[0])

        print(f"找到 {len(sorted_folders)} 个视频，按BV课程分组转换...\n")
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(self.executor, self.process_folder, f)
            for f in sorted_folders
        ]
        await asyncio.gather(*tasks)
        print("\n全部任务执行完成！")

    def start(self):
        asyncio.run(self.async_run())


if __name__ == "__main__":
    try:
        converter = BilibiliCacheConverter()
        converter.start()
    except Exception as e:
        print(f"\n程序崩溃：{str(e)}")
