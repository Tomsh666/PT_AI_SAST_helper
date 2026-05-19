# PT AI SAST Helper

Локальный LLM-триаж SARIF-отчётов от PT AI 5.4. Принимает SARIF, выдаёт для каждого finding'а вердикт `REAL` / `FP` с уверенностью 0–100 и развёрнутый разбор по запросу. Работает офлайн через локальную Ollama.


## Быстрый старт

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
ollama serve & ollama pull qwen2.5-coder:7b-instruct-q4
python main.py --help
```
