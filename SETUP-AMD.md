# AMD Radeon 890M — Ollama GPU setup (Windows)

Your **Ryzen AI 9 HX 370** can accelerate Ollama via the integrated **Radeon 890M**.
By default Ollama uses CPU only (~5–10 tok/s). With iGPU enabled: ~15–20 tok/s on 7B models.

## 1. System environment variables

Windows → Settings → System → About → Advanced system settings → Environment Variables

Add **User** variables:

```
OLLAMA_IGPU_ENABLE=1
```

Optional (test both on your machine):

```
OLLAMA_VULKAN=1
```

Some users report **better speed with Vulkan off** on Ollama 0.30+. If GPU is unstable, try `OLLAMA_VULKAN=0`.

Restart Ollama after changing variables (quit from system tray, reopen).

## 2. AMD Adrenalin — shared GPU memory

1. Open **AMD Software: Adrenalin Edition**
2. Gaming → Graphics → Memory
3. Set **Shared GPU Memory** to **16–20 GB** (you have 32 GB total RAM)

This lets the iGPU use enough RAM for `qwen2.5:7b-instruct` and `qwen2.5vl:7b`.

## 3. Verify GPU is used

```powershell
ollama run qwen2.5:7b-instruct "כתוב משפט אחד בעברית"
```

Open **Task Manager → Performance → GPU 0 → Compute** — you should see activity.

## 4. RAM tips (32 GB)

- Models run **one at a time** (vision first, then text) — the tool unloads between stages
- Close heavy browser tabs during jobs
- Do not run cloud + local editions simultaneously

## 5. Expected speed per product job

| Stage | Time |
|-------|------|
| Scrape + heuristics | ~10 s |
| Vision image filter | 30–90 s |
| rembg + WebP | 30–60 s |
| Hebrew copy (7B) | 30–90 s |
| **Total** | **~2–4 min** |
