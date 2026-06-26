"""
Stop Hook — Claude Code 会话结束时自动触发。
从对话上下文中尝试提取关键决策/约束，写入 vault 记忆快照。

环境变量 (Claude Code hooks 注入):
  CLAUDE_SESSION_ID    会话 ID
  对话内容通过 stdin 或 transcript 文件获取（取决于 hook 配置）
"""
import os
import sys
import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # 尝试从 stdin 读取对话摘要（如果 hook 传了）
    summary = ""
    if not sys.stdin.isatty():
        summary = sys.stdin.read().strip()

    # 如果有对话内容，尝试写入草稿记忆
    if summary and len(summary) > 100:
        vault = r"D:\Agent\Obsidian store"
        draft_dir = os.path.join(vault, "记忆")
        os.makedirs(draft_dir, exist_ok=True)

        date_str = datetime.date.today().isoformat()
        draft_file = os.path.join(draft_dir, f"_draft-{date_str}.md")

        content = f"""---
tags: [mem-decision, hot-30d, draft]
date: {date_str}
summary: 会话 {session_id} 自动蒸馏草稿
---

# 会话草稿 — {timestamp}

## 原始摘要
{summary[:3000]}

> ⚠️ 自动生成草稿，请用 /digest 确认或手动编辑。
"""
        with open(draft_file, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[HookDigest] 草稿已写入: {draft_file}")
    else:
        # 无对话内容，记录会话标记
        marker_dir = os.path.join(r"D:\Agent\Obsidian store", "记忆", ".sessions")
        os.makedirs(marker_dir, exist_ok=True)
        marker_file = os.path.join(marker_dir, f"{timestamp[:10]}_{session_id}.txt")
        with open(marker_file, "w") as f:
            f.write(f"session: {session_id}\nend: {timestamp}\n")
        print(f"[HookDigest] 会话标记: {marker_file}")


if __name__ == "__main__":
    main()
