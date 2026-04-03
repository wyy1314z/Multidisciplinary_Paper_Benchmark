"""
测试推荐模型在各 API 端点下的可用性。
用法:
    python test_model_availability.py

需要环境变量:
    OPENAI_API_KEY      — 用于 shubiaobiao / cstcloud 端点
    OPENROUTER_API_KEY  — 用于 OpenRouter 端点 (可选)
"""
import os, time, json, sys
from openai import OpenAI

TEST_PROMPT = "What is 1+1? Answer with just the number."

# ── 端点配置 ──
ENDPOINTS = {
    "shubiaobiao": {
        "base_url": "http://api.shubiaobiao.cn/v1",
        "api_key_env": "OPENAI_API_KEY",
    },
    "cstcloud": {
        "base_url": "https://uni-api.cstcloud.cn/v1",
        "api_key_env": "OPENAI_API_KEY",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
    },
}

# ── 推荐测试模型 ──
# (模型名, 优先尝试的端点列表)
MODELS_TO_TEST = [
    # 项目配置中已有的模型
    ("deepseek-v3",                     ["shubiaobiao", "cstcloud"]),
    ("deepseek/deepseek-chat-v3.1",     ["shubiaobiao", "cstcloud"]),
    ("deepseek/deepseek-r1-0528",       ["shubiaobiao", "cstcloud"]),
    ("qwen3-235b-a22b",                 ["shubiaobiao"]),
    ("qwen/qwen-2.5-72b-instruct",     ["shubiaobiao", "cstcloud"]),
    ("qwen/qwen3-max",                  ["shubiaobiao", "cstcloud"]),
    ("openai/gpt-4o-mini",              ["shubiaobiao", "cstcloud"]),
    ("openai/gpt-4.1-mini",            ["shubiaobiao", "cstcloud"]),
    ("deepseek-v3:671b-gw",            ["cstcloud"]),

    # OpenRouter 模型
    ("anthropic/claude-3.5-sonnet",     ["openrouter"]),
    ("anthropic/claude-3-haiku",        ["openrouter"]),
    ("meta-llama/llama-3.3-70b-instruct", ["openrouter"]),
    ("mistralai/mistral-large-2411",    ["openrouter"]),
    ("google/gemini-2.0-flash-exp:free", ["openrouter"]),
    ("google/gemini-2.0-flash-lite-001", ["openrouter"]),
    ("google/gemini-pro-1.5",           ["openrouter"]),
    ("x-ai/grok-2-1212",               ["openrouter"]),
    ("amazon/nova-pro-v1",              ["openrouter"]),
]


def test_model(client, model_name, endpoint_name, timeout=30):
    """测试单个模型是否可用，返回 (success, latency_ms, response_text, error)"""
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": TEST_PROMPT}],
            max_tokens=32,
            temperature=0.0,
            timeout=timeout,
        )
        latency = (time.time() - t0) * 1000
        content = resp.choices[0].message.content.strip() if resp.choices else ""
        return True, latency, content, None
    except Exception as e:
        latency = (time.time() - t0) * 1000
        err_msg = str(e)[:120]
        return False, latency, "", err_msg


def list_models(client, endpoint_name):
    """尝试获取端点支持的模型列表"""
    try:
        models = client.models.list()
        return [m.id for m in models.data]
    except Exception as e:
        return None


def main():
    print("=" * 80)
    print("  CrossDisc-Bench 模型可用性测试")
    print("=" * 80)

    # 初始化客户端
    clients = {}
    for ep_name, ep_cfg in ENDPOINTS.items():
        api_key = os.environ.get(ep_cfg["api_key_env"])
        if not api_key:
            print(f"\n[{ep_name}] SKIP — 环境变量 {ep_cfg['api_key_env']} 未设置")
            continue
        clients[ep_name] = OpenAI(
            base_url=ep_cfg["base_url"],
            api_key=api_key,
            max_retries=0,
        )
        print(f"\n[{ep_name}] 端点: {ep_cfg['base_url']} — KEY 已配置")

    if not clients:
        print("\n错误: 没有可用的 API Key，请设置环境变量后重试")
        sys.exit(1)

    # Step 1: 尝试获取模型列表
    print("\n" + "─" * 80)
    print("  Step 1: 查询各端点支持的模型列表")
    print("─" * 80)

    available_models_by_ep = {}
    for ep_name, client in clients.items():
        models = list_models(client, ep_name)
        if models:
            available_models_by_ep[ep_name] = models
            print(f"\n[{ep_name}] 共 {len(models)} 个模型可用:")
            for m in sorted(models)[:30]:
                print(f"    {m}")
            if len(models) > 30:
                print(f"    ... 共 {len(models)} 个 (仅显示前30)")
        else:
            print(f"\n[{ep_name}] 无法获取模型列表 (需逐个测试)")

    # Step 2: 逐个测试推荐模型
    print("\n" + "─" * 80)
    print("  Step 2: 逐个测试推荐模型的实际可用性")
    print("─" * 80)

    results = []
    for model_name, preferred_endpoints in MODELS_TO_TEST:
        tested = False
        for ep_name in preferred_endpoints:
            if ep_name not in clients:
                continue
            tested = True
            client = clients[ep_name]

            sys.stdout.write(f"\n  Testing: {model_name:45s} @ {ep_name:15s} ... ")
            sys.stdout.flush()

            ok, latency, resp, err = test_model(client, model_name, ep_name)

            status = "✅ OK" if ok else "❌ FAIL"
            print(f"{status}  ({latency:.0f}ms)  {resp[:30] if ok else err[:60]}")

            results.append({
                "model": model_name,
                "endpoint": ep_name,
                "success": ok,
                "latency_ms": round(latency),
                "response": resp[:50] if ok else "",
                "error": err if not ok else "",
            })

            if ok:
                break  # 成功即跳过其他端点

        if not tested:
            print(f"\n  Testing: {model_name:45s} — SKIP (无可用端点)")
            results.append({
                "model": model_name,
                "endpoint": "N/A",
                "success": False,
                "latency_ms": 0,
                "response": "",
                "error": "No API key for required endpoint",
            })

    # Step 3: 汇总
    print("\n" + "=" * 80)
    print("  测试结果汇总")
    print("=" * 80)

    ok_models = [r for r in results if r["success"]]
    fail_models = [r for r in results if not r["success"]]

    print(f"\n  ✅ 可用模型: {len(ok_models)}/{len(results)}")
    print(f"  ❌ 不可用:   {len(fail_models)}/{len(results)}")

    if ok_models:
        print(f"\n  {'模型':<45s} {'端点':<15s} {'延迟':>8s}")
        print("  " + "─" * 70)
        for r in ok_models:
            print(f"  {r['model']:<45s} {r['endpoint']:<15s} {r['latency_ms']:>6d}ms")

    if fail_models:
        print(f"\n  不可用模型:")
        for r in fail_models:
            print(f"  ❌ {r['model']:<45s} @ {r['endpoint']:<15s} — {r['error'][:50]}")

    # 保存结果
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model_availability_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  详细结果已保存至: {out_path}")


if __name__ == "__main__":
    main()
