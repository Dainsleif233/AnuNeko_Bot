import json
import os
import httpx

# 每个 QQ 用户/群组一个独立会话
user_sessions = {}
# 每个 QQ 用户/群组的当前模型
user_models = {}  # user_id: "Orange Cat" or "Exotic Shorthair"

# ============================================================
#             异步 httpx 请求封装
# ============================================================

def build_headers():
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://anuneko.com",
        "referer": "https://anuneko.com/",
        "user-agent": "Mozilla/5.0",
        "x-app_id": "com.anuttacon.neko",
        "x-client_type": "4",
        "x-device_id": "7b75a432-6b24-48ad-b9d3-3dc57648e3e3",
        "x-token": os.getenv("ANUNEKO_TOKEN"),
    }

    return headers


# ============================================================
#          创建新会话（使用 httpx 异步重写）
# ============================================================

async def create_new_session(user_id: str):
    headers = build_headers()
    model = user_models.get(user_id, "Orange Cat")
    data = json.dumps({"model": model})

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(os.getenv("CHAT_API_URL"), headers=headers, content=data)
            resp_json = resp.json()

        chat_id = resp_json.get("chat_id") or resp_json.get("id")
        if chat_id:
            user_sessions[user_id] = chat_id
            # 切换模型以确保一致性
            await switch_model(user_id, chat_id, model)
            return chat_id

    except Exception:
        return None

    return None


# ============================================================
#      切换模型（async）
# ============================================================

async def switch_model(user_id: str, chat_id: str, model_name: str):
    headers = build_headers()
    data = json.dumps({"chat_id": chat_id, "model": model_name})

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(os.getenv("SELECT_MODEL_URL"), headers=headers, content=data)
            if resp.status_code == 200:
                user_models[user_id] = model_name
                return True
    except:
        pass
    return False


# ============================================================
#      自动选分支（async）
# ============================================================

async def send_choice(msg_id: str):
    headers = build_headers()

    data = json.dumps({"msg_id": msg_id, "choice_idx": 0})

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(os.getenv("SELECT_CHOICE_URL"), headers=headers, content=data)
    except:
        pass


# ============================================================
#      核心：异步流式回复（超级稳定）
# ============================================================

async def stream_reply(session_uuid: str, text: str) -> str:
    headers = {
        "x-token": os.getenv("ANUNEKO_TOKEN"),
        "Content-Type": "text/plain",
    }

    url = os.getenv("STREAM_API_URL").format(uuid=session_uuid)
    data = json.dumps({"contents": [text]}, ensure_ascii=False)

    result = ""
    current_msg_id = None

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST", url, headers=headers, content=data
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    
                    # 处理错误响应
                    if not line.startswith("data: "):
                        try:
                            error_json = json.loads(line)
                            if error_json.get("code") == "chat_choice_shown":
                                return "⚠️ 检测到对话分支未选择，请重试或新建会话。"
                        except:
                            pass
                        continue

                    # 处理 data: {}
                    try:
                        raw_json = line[6:]
                        if not raw_json.strip():
                            continue
                            
                        j = json.loads(raw_json)

                        # 只要出现 msg_id 就更新，流最后一条通常是 assistmsg，也就是我们要的 ID
                        if "msg_id" in j:
                            current_msg_id = j["msg_id"]

                        # 如果有 'c' 字段，说明是多分支内容
                        # 格式如: {"c":[{"v":"..."},{"v":"...","c":1}]}
                        if "c" in j and isinstance(j["c"], list):
                            for choice in j["c"]:
                                # 默认选项 idx=0，可能显式 c=0 或隐式(无 c 字段)
                                idx = choice.get("c", 0)
                                if idx == 0:
                                    if "v" in choice:
                                        result += choice["v"]
                        
                        # 常规内容 (兼容旧格式或无分支情况)
                        elif "v" in j and isinstance(j["v"], str):
                            result += j["v"]

                    except:
                        continue
        
        # 流结束后，如果有 msg_id，自动确认选择第一项，确保下次对话正常
        if current_msg_id:
            await send_choice(current_msg_id)

    except Exception:
        return "请求失败，请稍后再试。"

    return result

# ---------------------------
#   /switch 切换模型
# ---------------------------

async def switch(id: str, arg: str):
    if "橘猫" in arg or "orange" in arg.lower():
        target_model = "Orange Cat"
        target_name = "橘猫"
    elif "黑猫" in arg or "exotic" in arg.lower():
        target_model = "Exotic Shorthair"
        target_name = "黑猫"
    else:
        return "请指定要切换的模型：橘猫 / 黑猫"

    # 获取当前会话ID，如果没有则新建
    if id not in user_sessions:
        chat_id = await create_new_session(id)
        if not chat_id:
             return "❌ 切换失败：无法创建会话"
    else:
        chat_id = user_sessions[id]

    success = await switch_model(id, chat_id, target_model)
    
    if success:
        return f"✨ 已切换为：{target_name}"
    else:
        return f"❌ 切换为 {target_name} 失败"


# ---------------------------
#   /new 创建新会话
# ---------------------------

async def new(id: str):
    new_id = await create_new_session(id)

    if new_id:
        model_name = "橘猫" if user_models.get(id) == "Orange Cat" else "黑猫"
        return f"✨ 已创建新的会话（当前模型：{model_name}）！"
    else:
        return "❌ 创建会话失败，请稍后再试。"


# ---------------------------
#   进行对话
# ---------------------------

async def chat(id: str, text: str):
    if not text:
        return "❗ 请输入内容，例如：你好"

    # 自动创建会话
    if id not in user_sessions:
        cid = await create_new_session(id)
        if not cid:
            return "❌ 创建会话失败，请稍后再试。"

    session_id = user_sessions[id]
    reply = await stream_reply(session_id, text)

    return reply

async def handle(id: str, content: str):
    text = content.lstrip()
    if text.startswith("/switch "):
        return await switch(id, text[8:])
    if text.startswith("/new"):
        return await new(id)
    return await chat(id, text)
