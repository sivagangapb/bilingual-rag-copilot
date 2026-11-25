# ---- Bilingual RAG Copilot: one container with app, data and models ----
FROM python:3.12-slim

# Hugging Face Spaces runs containers as user 1000; caches must be writable by it
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface \
    PYTHONUNBUFFERED=1 \
    PORT=7860
WORKDIR /app

# 1. Python packages. CPU-only PyTorch first: the default one bundles GPU libraries (+3 GB)
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && grep -v -E "^(torch|nvidia|triton)" requirements.txt > req-no-torch.txt \
 && pip install --no-cache-dir -r req-no-torch.txt

# 2. Code + raw documents (processed data is rebuilt in step 3)
COPY --chown=user src/ src/
COPY --chown=user web/ web/
COPY --chown=user data/raw/ data/raw/
RUN mkdir -p data/processed && chown -R user /app

# 3. Build chunks, download both models, cache embeddings -> fast start, no downloads later
USER user
RUN python src/warmup.py

# 4. Start the web server (the OpenAI key comes from the environment at runtime, never baked in)
EXPOSE 7860
CMD uvicorn app:app --app-dir src --host 0.0.0.0 --port ${PORT}
