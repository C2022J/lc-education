# src/tools/mineru_parser.py
import requests
import time
import zipfile
import io
import os
import re
from pathlib import Path
from src.config.settings import settings

MINERU_BASE_URL = "https://mineru.net/api/v4"

def submit_pdf_to_mineru(file_path: str, data_id: str = "math_exam") -> str:
    """
    步骤 1: 采用本地文件上传模式 (Batch File Extract)
    获取上传 URL -> PUT 文件 -> 获取 task_id
    """
    print("\n" + "-" * 40)
    print(f"📤 [MinerU 解析器] 开始提交流程...")
    print(f"  📄 目标文件: {os.path.basename(file_path)}")

    # 1. 申请上传链接
    apply_url = f"{MINERU_BASE_URL}/file-urls/batch"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.MINERU_API_TOKEN}"
    }
    file_name = os.path.basename(file_path)
    data = {
        "files": [{"name": file_name, "data_id": data_id}],
        "model_version": "vlm",  # 强力推荐 VLM 模型处理数学试卷
        "enable_formula": True,
        "enable_table": True
    }

    res = requests.post(apply_url, headers=headers, json=data)
    if res.status_code != 200 or res.json().get("code") != 0:
        raise Exception(f"❌ MinerU 申请上传失败: {res.text}")

    batch_id = res.json()["data"]["batch_id"]
    upload_url = res.json()["data"]["file_urls"][0]
    print(f"  🔗 成功获取云端专属上传通道 (Batch ID: {batch_id})")

    # 2. PUT 文件到 OSS
    print(f"  ⬆️ 正在将本地文件推送至云端解析引擎...")
    with open(file_path, 'rb') as f:
        upload_res = requests.put(upload_url, data=f)
        if upload_res.status_code != 200:
            raise Exception("❌ 文件上传云端失败")

    print(f"✅ [MinerU 解析器] 文件提交成功，进入解析队列！")
    print("-" * 40 + "\n")
    return batch_id


def poll_mineru_result(batch_id: str, timeout=600, interval=5) -> str:
    """
    步骤 2: 轮询解析结果，并下载解压提取 Markdown 与 图片
    """
    headers = {"Authorization": f"Bearer {settings.MINERU_API_TOKEN}"}
    start_time = time.time()
    
    # 定位本项目的物理输出路径，改为独立的 assets 文件夹！
    base_dir = Path(__file__).parent.parent.parent.resolve()
    assets_dir = base_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    print(f"📡 [MinerU 轮询器] 开始监听云端解析状态 (Batch ID: {batch_id})...")

    while time.time() - start_time < timeout:
        res = requests.get(f"{MINERU_BASE_URL}/extract-results/batch/{batch_id}", headers=headers)
        result = res.json()

        if result.get("code") != 0:
            raise Exception(f"❌ 轮询报错: {result.get('msg')}")

        file_info = result["data"]["extract_result"][0]
        state = file_info["state"]

        if state == "done":
            zip_url = file_info["full_zip_url"]
            print(f"\n🎉 [MinerU 轮询器] 云端解析完成！")
            print(f"  📥 正在下载结构化 ZIP 数据包...")

            # 下载 zip 并直接在内存中解压提取
            zip_res = requests.get(zip_url)
            md_content = ""
            img_count = 0
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 调试：打印 ZIP 文件内容清单 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            print(f"\n  📋 [DEBUG] ZIP 文件完整清单:")
            with zipfile.ZipFile(io.BytesIO(zip_res.content)) as z:
                all_files = z.namelist()
                print(f"      总文件数: {len(all_files)}")
                for idx, item in enumerate(all_files, 1):
                    file_size = z.getinfo(item).file_size
                    print(f"      [{idx}] {item} ({file_size} bytes)")
            
            print(f"\n  📦 开始解压并提取静态资产至本地 {assets_dir.name} 目录:")
            with zipfile.ZipFile(io.BytesIO(zip_res.content)) as z:
                for item in z.namelist():
                    if item.endswith('.md'):
                        md_content = z.read(item).decode('utf-8')
                        print(f"    📄 提取文本: 发现核心 Markdown 文件 (长度: {len(md_content)} 字符)")
                    elif item.startswith('images/') or item.endswith(('.png', '.jpg', '.jpeg')):
                        # 将图片提取到 backend/assets/ 目录下
                        z.extract(item, path=str(assets_dir))
                        img_count += 1
                        actual_path = assets_dir / item
                        print(f"    🖼️ 提取图片: {item}")
                        print(f"       实际保存路径: {actual_path}")
                        print(f"       文件存在: {actual_path.exists()}")
            
            print(f"\n  ✅ 提取完毕！共获得 1 个文本文件，{img_count} 张图片。")

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 调试：Markdown 链接分析 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            print(f"\n  🔍 [DEBUG] 分析 Markdown 中的图片链接：")
            import re as regex
            original_links = regex.findall(r'!\[.*?\]\((.*?)\)', md_content)
            print(f"      原始链接总数: {len(original_links)}")
            print(f"      原始链接列表:")
            for i, link in enumerate(original_links, 1):
                print(f"        [{i}] {link}")
            
            # 【路径重写】：让 Markdown 链接指向我们干净的 assets 目录
            # MinerU 原本写的是: ![描述](images/xxx.jpg)
            # 我们要把它改成: ![描述](assets/images/xxx.jpg)
            print(f"\n  🔗 正在重写 Markdown 中的图片链接锚点...")
            print(f"     应用正则: r'!\\[(.*?)\\]\\((?:.*?/)?images/(.*?)\\)' -> r'![\\1](assets/images/\\2)'")
            
            md_content_before = md_content
            md_content = re.sub(
                r'!\[(.*?)\]\((?:.*?/)?images/(.*?)\)', 
                r'![\1](assets/images/\2)', 
                md_content
            )
            
            # 重新提取替换后的链接
            new_links = regex.findall(r'!\[.*?\]\((.*?)\)', md_content)
            print(f"     替换后链接总数: {len(new_links)}")
            print(f"     替换后链接列表:")
            for i, link in enumerate(new_links, 1):
                print(f"        [{i}] {link}")
            
            # 检查链接变化
            if len(original_links) != len(new_links):
                print(f"\n  ⚠️ [警告] 链接数量变化: {len(original_links)} -> {len(new_links)}")
                print(f"           未被替换的链接可能包含: {set(original_links) - set([l.replace('assets/', '') for l in new_links if 'assets/' in l])}")
            
            print(f"\n✅ [MinerU 解析器] 全流程执行完毕，数据已准备就绪！\n")
            return md_content

        elif state == "failed":
            raise Exception(f"❌ 解析彻底失败: {file_info.get('err_msg')}")

        elif state == "running":
            progress = file_info.get("extract_progress", {})
            extracted = progress.get('extracted_pages', 0)
            total = progress.get('total_pages', 0)
            elapsed = int(time.time() - start_time)
            print(f"  ⏳ [耗时 {elapsed}s] 云端深度解析中... 当前进度: {extracted}/{total} 页")

        time.sleep(interval)

    raise Exception("❌ API 解析超时！")