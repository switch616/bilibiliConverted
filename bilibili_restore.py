import os
from dotenv import load_dotenv

# 加载同一套配置
load_dotenv()

class BilibiliCacheRestorer:
    def __init__(self):
        self.cache_root = os.getenv("BILIBILI_CACHE_DIR").strip()
        if not os.path.isdir(self.cache_root):
            raise Exception(f"缓存目录不存在：{self.cache_root}")

    def clean_cache(self):
        """
        清理所有生成的文件：
        1. 删除 .m4s.bak 备份文件
        2. 删除残留的 _temp.m4s 临时文件
        """
        print("开始还原缓存目录，清理生成的备份/临时文件...")
        deleted_count = 0

        # 遍历所有子文件夹
        for root, dirs, files in os.walk(self.cache_root):
            for file in files:
                file_path = os.path.join(root, file)
                # 匹配需要删除的文件规则
                if file.endswith(".m4s.bak") or file.endswith("_temp.m4s"):
                    try:
                        os.remove(file_path)
                        print(f"已删除：{file_path}")
                        deleted_count += 1
                    except Exception as e:
                        print(f"删除失败：{file_path}，错误：{str(e)}")

        print(f"\n还原完成！共清理文件：{deleted_count} 个")
        print("缓存目录已恢复为原始状态")

if __name__ == "__main__":
    try:
        restorer = BilibiliCacheRestorer()
        restorer.clean_cache()
    except Exception as e:
        print(f"还原程序崩溃：{str(e)}")